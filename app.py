"""Painel de transacoes do AppTicket, executavel localmente e na Vercel."""
import base64, contextlib, csv, hashlib, hmac, io, json, os, secrets, sqlite3, sys, time, urllib.error, urllib.parse, urllib.request

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response

DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(DIR, "dados.db")
EVENTO = "36766"
COLS = ["id_transacao", "id_presence", "nome", "cpf", "email", "telefone", "cargo", "tipo_ingresso",
        "qtde_tickets", "total", "liquido", "desconto", "pagamento", "status", "status_code", "status_api",
        "origem", "data", "erro"]


def carregar_env():
    """Carrega o .env local sem adicionar dependencias ao projeto."""
    path = os.path.join(DIR, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                chave, valor = linha.split("=", 1)
                os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


carregar_env()

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ---------- banco ----------
@contextlib.contextmanager
def db():
    """Conexao que commita e FECHA no fim (senao vaza handle a cada request)."""
    c = sqlite3.connect(DB, timeout=30)
    try:
        cols = {r[1] for r in c.execute("PRAGMA table_info(resultado)")}
        adicionadas = set(COLS) - cols if cols else set()
        for coluna in adicionadas:
            c.execute(f"ALTER TABLE resultado ADD COLUMN {coluna} TEXT")
        c.execute(f"CREATE TABLE IF NOT EXISTS resultado (id_transacao TEXT PRIMARY KEY, "
                  f"{', '.join(k + ' TEXT' for k in COLS[1:])})")
        if "desconto" in adicionadas:
            # Preserva a coleta atual e completa o novo campo a partir do snapshot local existente.
            try:
                with open(os.path.join(DIR, "dados_completos.json"), encoding="utf-8") as f:
                    bruto = json.load(f)
                linhas = bruto.get("data", bruto) if isinstance(bruto, dict) else bruto
                c.executemany("UPDATE resultado SET desconto=? WHERE id_transacao=?",
                              [(str(r.get("value_discount") or 0), str(r["id_transaction"]))
                               for r in linhas if r.get("id_transaction") is not None])
            except (OSError, ValueError, TypeError):
                pass  # futuras coletas preenchem o campo normalmente
        yield c
        c.commit()
    finally:
        c.close()


def usar_supabase():
    """Na Vercel o filesystem e efemero; localmente o SQLite continua disponivel."""
    return bool(os.environ.get("VERCEL")) or os.environ.get("STORAGE_BACKEND", "sqlite").lower() == "supabase"


def _supabase(method, recurso, query="", body=None, prefer=None, alcance=None):
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    chave = os.environ.get("SUPABASE_SECRET_KEY", "")
    schema = os.environ.get("SUPABASE_SCHEMA", "appticket")
    if not url or not chave or "SUBSTITUA" in url or "SUBSTITUA" in chave:
        raise RuntimeError("Configure SUPABASE_URL e SUPABASE_SECRET_KEY no ambiente.")
    headers = {"apikey": chave, "Content-Type": "application/json"}
    # Chaves service_role antigas sao JWTs; as novas sb_secret_* autenticam pelo apikey.
    if chave.startswith("eyJ"):
        headers["Authorization"] = "Bearer " + chave
    headers["Accept-Profile" if method == "GET" else "Content-Profile"] = schema
    if prefer:
        headers["Prefer"] = prefer
    if alcance:
        headers["Range"] = alcance
    dados = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(f"{url}/rest/v1/{recurso}{query}", data=dados, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            bruto = res.read()
            return json.loads(bruto) if bruto else None
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"Supabase retornou HTTP {e.code}: {detalhe[:500]}") from e
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise RuntimeError(f"Nao foi possivel conectar ao Supabase: {e}") from e


def _listar_supabase(query):
    objetos = []
    while True:
        inicio = len(objetos)
        lote = _supabase("GET", "transacoes", query, alcance=f"{inicio}-{inicio + 999}") or []
        objetos.extend(lote)
        if len(lote) < 1000:
            return objetos


def carregar_dados():
    if usar_supabase():
        campos = urllib.parse.quote(",".join(COLS), safe=",")
        objetos = _listar_supabase(f"?select={campos}&order=data.desc")
        rows = [[obj.get(k) for k in COLS] for obj in objetos]
        return rows, sum(bool(obj.get("erro")) for obj in objetos)
    with db() as c:
        rows = c.execute(f"SELECT {','.join(COLS)} FROM resultado ORDER BY data DESC").fetchall()
        erros = c.execute("SELECT COUNT(*) FROM resultado WHERE erro IS NOT NULL AND erro<>''").fetchone()[0]
    return rows, erros


def ja_coletados():
    if usar_supabase():
        objetos = _listar_supabase("?select=id_transacao,erro")
        return [r["id_transacao"] for r in objetos if not r.get("erro")]
    with db() as c:
        return [r[0] for r in c.execute("SELECT id_transacao FROM resultado WHERE erro IS NULL OR erro=''")]


def gravar(linhas):
    """Upsert do que o navegador coletou. Retorna quantas linhas gravou."""
    if not isinstance(linhas, list):
        raise ValueError("A coleta precisa ser uma lista de transacoes.")
    objetos = [{k: str(r.get(k)) if r.get(k) is not None else None for k in COLS} for r in linhas]
    if usar_supabase():
        for inicio in range(0, len(objetos), 150):
            _supabase("POST", "transacoes", "?on_conflict=id_transacao", objetos[inicio:inicio + 150],
                      "resolution=merge-duplicates,return=minimal")
        return len(objetos)
    vals = [tuple(r[k] for k in COLS) for r in objetos]
    with db() as c:
        c.executemany(f"INSERT OR REPLACE INTO resultado ({','.join(COLS)})"
                      f" VALUES ({','.join('?' * len(COLS))})", vals)
    return len(vals)


def limpar_dados():
    if usar_supabase():
        _supabase("DELETE", "transacoes", "?id_transacao=not.is.null", prefer="return=minimal")
    else:
        with db() as c:
            c.execute("DELETE FROM resultado")


# ---------- script que roda no console do navegador ----------
COLETOR = r"""(async () => {
  const EV = '__EV__';
  const JA = new Set(__JA__);
  const CONC = 8;  // ponytail: paralelismo fixo; baixe se a API comecar a recusar
  // grupos do painel; status desconhecido vira "Status N" em vez de sumir
  const STATUS = {'1': 'Checkout iniciado', '2': 'Pendente', '3': 'Pagamento expirado',
                  '4': 'Compra aprovada', '5': 'Pagamento expirado', '7': 'Compra cancelada'};
  const X = decodeURIComponent((document.cookie.match(/XSRF-TOKEN=([^;]+)/) || [])[1] || '');
  const API = {credentials: 'include', headers: {'Accept': 'application/json', 'X-Xsrf-Token': X}};

  let bruto;
  try {
    bruto = await (await fetch('https://apiv2.appticket.com.br/api/kpi/' + EV + '/transaction/list', API)).json();
  } catch (err) {
    return console.error('nao consegui ler a lista de transacoes. Rode este script na aba '
      + 'https://appticket.com.br/areaProdutor/lista/participantes/?ev=' + EV + '&origin=new', err);
  }
  const d = bruto.data || bruto;
  const lista = [bruto, d, d.transactions, d.list, d.data].find(Array.isArray) || [];
  if (!lista.length) return console.error('lista vazia ou formato inesperado:', bruto);

  const IDS = lista.filter(t => !JA.has(String(t.id_transaction)));
  console.log(lista.length + ' transacoes no evento, ' + IDS.length + ' a coletar'
    + (JA.size ? ' (' + JA.size + ' ja coletadas antes)' : ''));
  if (!IDS.length) return;

  const out = [];
  const um = async (t) => {
    const cod = String(t.status_transaction);
    const r = {id_transacao: String(t.id_transaction), id_presence: null, erro: null,
               status_code: cod, status: STATUS[cod] || ('Status ' + cod),
               data: t.date_start, origem: t.origin, qtde_tickets: t.qtde_ticket,
               pagamento: t.payment_type || t.form_pay, total: t.value_total,
               desconto: t.value_discount,
               liquido: t.value_liquid, nome: t.name_user, email: t.email_user};
    try {
      const det = await (await fetch(
        'https://apiv2.appticket.com.br/api/transaction/detail/' + r.id_transacao, API)).json();
      const tr = (det.data || {}).transaction || {};
      r.status_api = tr.status_normalized || null;
      r.desconto = tr.value_discount ?? r.desconto;
      const p = ((det.data || {}).presences || [])[0];
      if (!p) return r;  // compra iniciada / sem ingresso: nao ha o que enriquecer, nao e erro
      r.id_presence = String(p.id_presence);
      r.tipo_ingresso = p.product_sector;
      const o = await (await fetch('/areaProdutor/lista/participantes/getOrder.php',
        {method: 'POST', credentials: 'include',
         headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                   'X-Requested-With': 'XMLHttpRequest'},
         body: 'idp=' + r.id_presence})).json();
      const a = (o.attendee || [])[0];
      if (!a) throw new Error('attendee vazio');
      const e = {};
      (a.extras || []).forEach(x => e[String(x.id_form_event)] = x.answer);
      Object.assign(r, {nome: a.name || r.nome, email: a.email_user || r.email,
                        tipo_ingresso: a.product_sector || r.tipo_ingresso,
                        telefone: e['13146'], cargo: e['13149'], cpf: e['13145']});
    } catch (err) {
      r.erro = String((err && err.message) || err).slice(0, 300);
    }
    return r;
  };
  const t0 = performance.now();
  for (let k = 0; k < IDS.length; k += CONC) {
    out.push(...await Promise.all(IDS.slice(k, k + CONC).map(um)));
    console.log(out.length + '/' + IDS.length);
  }
  console.log('terminou em ' + Math.round((performance.now() - t0) / 1000) + 's, '
    + out.filter(r => r.erro).length + ' com erro');

  try {
    const res = await fetch(__BASE__ + '/ingest',
      {method: 'POST', headers: {'Content-Type': 'text/plain', 'X-Ingest-Token': '__TOKEN__'}, body: JSON.stringify(out)});
    const resposta = await res.text();
    if (!res.ok) throw new Error('app respondeu HTTP ' + res.status + ': ' + resposta);
    console.log('%c enviado para o app: ' + resposta + ' ', 'background:#047857;color:#fff');
  } catch (err) {
    console.warn('app inacessivel, baixando coleta.json para importacao manual', err);
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(out)], {type: 'application/json'}));
    a.download = 'coleta.json';
    a.click();
  }
})()"""


def coletor(tudo=False, evento=EVENTO, token="", base_url=""):
    return (COLETOR.replace("__EV__", evento)
                   .replace("__TOKEN__", token)
                   .replace("__BASE__", json.dumps(base_url.rstrip("/")))
                   .replace("__JA__", json.dumps([] if tudo else ja_coletados())))


def autenticar_supabase(usuario, senha):
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    chave = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
    schema = os.environ.get("SUPABASE_SCHEMA", "appticket")
    if not url or not chave or "SUBSTITUA" in url or "SUBSTITUA" in chave:
        return False, "Configure SUPABASE_URL e SUPABASE_PUBLISHABLE_KEY no arquivo .env."
    req = urllib.request.Request(
        url + "/rest/v1/rpc/autenticar_usuario",
        data=json.dumps({"p_usuario": usuario, "p_senha": senha}).encode(),
        headers={"apikey": chave, "Content-Type": "application/json", "Content-Profile": schema}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.load(res) is True, "Usuário ou senha inválidos."
    except urllib.error.HTTPError as e:
        try:
            erro = json.loads(e.read())
        except (ValueError, OSError):
            erro = {}
        if erro.get("code") == "PGRST106":
            return False, f"O schema {schema} não está exposto na Data API do Supabase."
        if erro.get("code") == "PGRST202":
            return False, f"A função autenticar_usuario não foi encontrada no schema {schema}."
        if e.code in (401, 403):
            return False, "A chave do Supabase não foi aceita ou não possui permissão."
        return False, "Não foi possível autenticar. Execute as migrations e confira o .env."
    except (OSError, ValueError):
        return False, "Não foi possível conectar ao Supabase."


# ---------- autenticacao stateless ----------
def _segredo_app():
    segredo = os.environ.get("APP_SESSION_SECRET", "")
    if len(segredo) < 32 or "SUBSTITUA" in segredo:
        raise RuntimeError("Configure APP_SESSION_SECRET com pelo menos 32 caracteres.")
    return segredo.encode()


def assinar_token(tipo, sujeito="", segundos=7200):
    payload = json.dumps({"tipo": tipo, "sub": sujeito, "exp": int(time.time()) + segundos,
                          "nonce": secrets.token_urlsafe(8)}, separators=(",", ":")).encode()
    codificado = base64.urlsafe_b64encode(payload).rstrip(b"=")
    assinatura = hmac.new(_segredo_app(), codificado, hashlib.sha256).digest()
    return (codificado + b"." + base64.urlsafe_b64encode(assinatura).rstrip(b"=")).decode()


def validar_token(token, tipo):
    try:
        codificado, assinatura = token.encode().split(b".", 1)
        esperado = hmac.new(_segredo_app(), codificado, hashlib.sha256).digest()
        recebido = base64.urlsafe_b64decode(assinatura + b"=" * (-len(assinatura) % 4))
        if not hmac.compare_digest(recebido, esperado):
            return None
        payload = json.loads(base64.urlsafe_b64decode(codificado + b"=" * (-len(codificado) % 4)))
        if payload.get("tipo") == tipo and payload.get("exp", 0) > time.time():
            return payload.get("sub", "") or True
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeError, RuntimeError):
        pass
    return None


def usuario_sessao(request):
    return validar_token(request.cookies.get("pomin_session", ""), "session")


def nao_autorizado():
    return JSONResponse({"ok": False, "erro": "Autenticacao necessaria."}, status_code=401)


def url_publica(request):
    if os.environ.get("APP_BASE_URL"):
        return os.environ["APP_BASE_URL"].rstrip("/")
    protocolo = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc)).split(",")[0].strip()
    return f"{protocolo}://{host}"


def cookie_seguro(request):
    return bool(os.environ.get("VERCEL")) or request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


@app.get("/", response_class=HTMLResponse)
async def inicio(request: Request):
    return HTMLResponse(PAGINA if usuario_sessao(request) else LOGIN_PAGE)


@app.get("/logout")
async def logout():
    resposta = RedirectResponse("/", status_code=302)
    resposta.delete_cookie("pomin_session", path="/")
    return resposta


@app.post("/login")
async def login(request: Request):
    try:
        dados_login = await request.json()
        usuario = str(dados_login.get("usuario", "")).strip()
        senha = str(dados_login.get("senha", ""))
    except (ValueError, TypeError, AttributeError):
        return JSONResponse({"ok": False, "erro": "Dados invalidos."}, status_code=400)
    if not usuario or not senha:
        return JSONResponse({"ok": False, "erro": "Informe usuario e senha."}, status_code=400)
    ok, erro = autenticar_supabase(usuario, senha)
    if not ok:
        return JSONResponse({"ok": False, "erro": erro}, status_code=401)
    try:
        horas = max(1, int(os.environ.get("APP_SESSION_HOURS", "12")))
        token = assinar_token("session", usuario, horas * 3600)
    except (ValueError, RuntimeError) as e:
        return JSONResponse({"ok": False, "erro": str(e)}, status_code=500)
    resposta = JSONResponse({"ok": True})
    resposta.set_cookie("pomin_session", token, max_age=horas * 3600, path="/", httponly=True,
                        samesite="lax", secure=cookie_seguro(request))
    return resposta


@app.get("/coletor.js", response_class=PlainTextResponse)
async def baixar_coletor(request: Request, tudo: str | None = None, ev: str = EVENTO):
    if not usuario_sessao(request):
        return nao_autorizado()
    token = assinar_token("ingest", segundos=7200)
    return PlainTextResponse(coletor(tudo is not None, ev, token, url_publica(request)))


@app.get("/dados")
async def obter_dados(request: Request):
    if not usuario_sessao(request):
        return nao_autorizado()
    try:
        rows, erros = carregar_dados()
        return JSONResponse({"cols": COLS, "rows": rows, "erros": erros, "evento": EVENTO})
    except RuntimeError as e:
        return JSONResponse({"ok": False, "erro": str(e)}, status_code=500)


@app.get("/export.csv")
async def exportar(request: Request):
    if not usuario_sessao(request):
        return nao_autorizado()
    try:
        rows, _ = carregar_dados()
    except RuntimeError as e:
        return JSONResponse({"ok": False, "erro": str(e)}, status_code=500)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(COLS)
    w.writerows(rows)
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="transacoes.csv"'})


@app.post("/ingest", response_class=PlainTextResponse)
async def ingest(request: Request):
    token_ok = validar_token(request.headers.get("X-Ingest-Token", ""), "ingest") is not None
    if not usuario_sessao(request) and not token_ok:
        return nao_autorizado()
    try:
        n = gravar(await request.json())
        return PlainTextResponse(f"{n} linhas gravadas")
    except (ValueError, TypeError, RuntimeError, json.JSONDecodeError) as e:
        return PlainTextResponse(f"erro: {e}", status_code=400,
                                 headers={"Access-Control-Allow-Origin": "*"})
    except Exception as e:
        print(f"Erro inesperado no ingest: {type(e).__name__}: {e}", file=sys.stderr)
        return PlainTextResponse("erro interno ao gravar a coleta; consulte os logs da Vercel",
                                 status_code=500, headers={"Access-Control-Allow-Origin": "*"})


@app.post("/limpar")
async def limpar(request: Request):
    if not usuario_sessao(request):
        return nao_autorizado()
    try:
        limpar_dados()
        return JSONResponse({"ok": True})
    except RuntimeError as e:
        return JSONResponse({"ok": False, "erro": str(e)}, status_code=500)


LOGIN_PAGE = r"""<!doctype html><html lang=pt-BR><meta charset=utf-8>
<title>Acesso | Relatórios Grupo Pomin</title><meta name=viewport content="width=device-width,initial-scale=1">
<style>
@import url('https://fonts.googleapis.com/css2?family=Oxanium:wght@300;400;500;600;700&display=swap');
:root{--bg:205 40% 98%;--ink:215 25% 14%;--card:0 0% 100%;--primary:209 84% 36%;--primary-fg:0 0% 100%;--muted:215 14% 45%;--line:210 25% 90%;--accent:207 80% 94%;--danger:0 75% 55%}
*{box-sizing:border-box}body,button,input{font-family:Oxanium,system-ui,sans-serif}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:20px;background:radial-gradient(circle at 90% 90%,hsl(207 80% 85%/.35),transparent 42%),hsl(var(--bg));color:hsl(var(--ink))}
.login{width:min(100%,390px);padding:30px;background:hsl(var(--card));border:1px solid hsl(var(--line));border-radius:8px}.brand{display:flex;align-items:center;gap:12px;margin-bottom:30px}.mark{width:36px;height:36px;display:grid;place-items:center;border-radius:5px;background:linear-gradient(135deg,hsl(var(--primary)),hsl(197 71% 70%));color:hsl(var(--primary-fg));font-weight:700}.brand b{display:block}.brand small{color:hsl(var(--muted));font-size:11px;text-transform:uppercase;letter-spacing:.08em}h1{font-size:23px;letter-spacing:-.03em;margin:0 0 6px}p{color:hsl(var(--muted));font-size:13px;margin:0 0 24px}label{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:hsl(var(--muted));margin:14px 0 6px}input{width:100%;padding:11px;border:1px solid hsl(var(--line));border-radius:5px;font-size:14px;outline:none}input:focus{border-color:hsl(var(--primary));box-shadow:0 0 0 3px hsl(var(--accent))}button{width:100%;margin-top:20px;padding:11px;border:0;border-radius:5px;background:hsl(var(--primary));color:hsl(var(--primary-fg));font-weight:600;cursor:pointer}button:disabled{opacity:.6;cursor:wait}#erro{min-height:20px;margin:12px 0 0;color:hsl(var(--danger));font-size:12px}
</style><main class=login><div class=brand><span class=mark>P</span><span><b>Grupo Pomin</b><small>Relatórios AppTicket</small></span></div><h1>Bem-vindo</h1><p>Entre com as credenciais cadastradas para acessar o painel.</p>
<form id=form><label for=usuario>Usuário</label><input id=usuario autocomplete=username required><label for=senha>Senha</label><input id=senha type=password autocomplete=current-password required><button id=entrar>Entrar</button><div id=erro aria-live=polite></div></form></main>
<script>form.onsubmit=async e=>{e.preventDefault();entrar.disabled=true;erro.textContent='';try{const r=await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({usuario:usuario.value,senha:senha.value})}),d=await r.json();if(!r.ok)throw Error(d.erro||'Não foi possível entrar.');location.reload()}catch(e){erro.textContent=e.message;entrar.disabled=false}}</script></html>"""


PAGINA = r"""<!doctype html><html lang=pt-BR><meta charset=utf-8>
<title>Relatórios AppTicket | Grupo Pomin</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
@import url('https://fonts.googleapis.com/css2?family=Oxanium:wght@300;400;500;600;700&display=swap');
:root{--bg:205 40% 98%;--ink:215 25% 14%;--card:210 25% 98%;--pop:0 0% 100%;--primary:209 84% 36%;--primary-fg:0 0% 100%;--glow:197 71% 70%;--secondary:210 40% 96%;--muted:210 30% 96%;--ink2:215 14% 45%;--accent:207 80% 94%;--line:210 25% 90%;--ok:160 70% 38%;--warn:38 92% 50%;--danger:0 75% 55%;--rose:346 70% 55%;--indigo:215 60% 50%;--radius:5px;--sb:64px;--sb-open:240px}
html.dark{--bg:0 0% 2.7%;--ink:210 17% 92%;--card:220 10% 9%;--pop:240 7% 6%;--primary:197 71% 70%;--primary-fg:207 60% 8%;--secondary:207 28% 14%;--muted:207 28% 14%;--ink2:215 14% 60%;--accent:197 50% 18%;--line:207 22% 17%;--ok:160 60% 45%;--warn:38 92% 55%;--danger:0 70% 50%}
*{box-sizing:border-box}html{color-scheme:light}html.dark{color-scheme:dark}
body,button,input,select,textarea{font-family:Oxanium,system-ui,sans-serif}body{font-size:14px;line-height:1.45;margin:0;background:radial-gradient(circle at 95% 95%,hsl(207 80% 85%/.25),transparent 45%),hsl(var(--bg));color:hsl(var(--ink));-webkit-font-smoothing:antialiased}
button,input,select,textarea,summary{outline:none}button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,summary:focus-visible{box-shadow:0 0 0 2px hsl(var(--bg)),0 0 0 4px hsl(var(--primary))}
.sidebar{position:fixed;inset:0 auto 0 0;width:var(--sb);background:#FFFFFF;border-right:1px solid hsl(var(--line)/.7);z-index:20;overflow:hidden;transition:width .5s cubic-bezier(.32,.72,0,1);display:flex;flex-direction:column}.dark .sidebar{background:#070707}.sidebar:hover{width:var(--sb-open)}
.brand{height:64px;display:flex;align-items:center;gap:12px;padding:0 18px;white-space:nowrap;border-bottom:1px solid hsl(var(--line)/.6)}.brand-mark{width:28px;height:28px;flex:0 0 28px;border-radius:5px;background:linear-gradient(135deg,hsl(var(--primary)),hsl(var(--glow)));display:grid;place-items:center;color:hsl(var(--primary-fg));font-weight:700}.brand b{font-size:14px;letter-spacing:.02em}.brand small{display:block;font-size:10px;text-transform:uppercase;letter-spacing:.08em}
.sidebar nav{padding:14px 9px;display:grid;gap:5px}.sidebar nav button{height:42px;display:flex;align-items:center;gap:13px;width:100%;border:1px solid transparent;background:none;color:hsl(var(--ink2));border-radius:5px;padding:0 11px;cursor:pointer;white-space:nowrap;font:inherit;text-align:left}.sidebar nav button:hover{background:hsl(var(--ink)/.04);color:hsl(var(--ink))}.sidebar nav button.on{color:hsl(var(--ink));font-weight:600;background:linear-gradient(88.76deg,rgba(76,124,149,.08) 1.14%,rgba(76,124,149,.10) 98.42%);border-color:rgba(76,124,149,.30)}.nav-ico{width:18px;flex:0 0 18px;text-align:center;font-size:16px}
header{position:fixed;top:0;left:var(--sb);right:0;height:64px;z-index:15;display:flex;align-items:center;gap:12px;padding:0 24px;background:#FFFFFF;border-bottom:1px solid hsl(var(--line)/.65)}header strong{font-weight:600}header small{margin-left:auto;color:hsl(var(--ink2))}.logout{color:hsl(var(--ink2));text-decoration:none;font-size:12px;padding:6px 9px;border-radius:5px}.logout:hover{background:hsl(var(--muted));color:hsl(var(--ink))}
main{margin-left:var(--sb);padding:76px 12px 12px;min-height:100vh;transition:margin-left .5s cubic-bezier(.32,.72,0,1)}.sidebar:hover~header+main{margin-left:var(--sb-open)}main>section{display:none;background:hsl(var(--pop));border:1px solid hsl(var(--line)/.6);border-radius:5px;padding:24px;min-height:calc(100vh - 88px);max-width:1440px;margin:0 auto}main>section.on{display:block}
.pagehead{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:24px}.pagehead h1{font-size:24px;line-height:1.2;margin:0;font-weight:600;letter-spacing:-.03em}.pagehead p{margin:6px 0 0;color:hsl(var(--ink2));max-width:700px}.eyebrow,.k .rot{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:hsl(var(--ink2));font-weight:500}
.filterbar{display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding:12px;border:1px solid hsl(var(--line)/.7);border-radius:6px;background:hsl(var(--card));margin-bottom:18px}.filter-label{font-size:12px;color:hsl(var(--ink2))}.pills{display:flex;gap:3px;flex-wrap:wrap;border-radius:5px;padding:3px;background:hsl(var(--muted)/.6)}.pills button,.tog button,.dtabs button{border:0;background:none;color:hsl(var(--ink2));padding:7px 12px;border-radius:5px;cursor:pointer;font:inherit;font-size:12px}.pills button.on,.tog button.on,.dtabs button.on{background:hsl(var(--pop));color:hsl(var(--ink));font-weight:600;box-shadow:0 1px 3px hsl(var(--ink)/.08)}
.atualizado{font-size:12px;color:hsl(var(--ink2));margin:0 0 18px}.custom{display:none;gap:8px;align-items:center}.custom.on{display:flex}input[type=date],input[type=text],select{padding:9px 10px;border:1px solid hsl(var(--line));border-radius:5px;background:hsl(var(--pop));color:hsl(var(--ink));font:inherit}
.summary{display:flex;gap:10px;align-items:flex-start;padding:14px 16px;border-left:3px solid hsl(var(--primary));background:hsl(var(--accent)/.65);border-radius:5px;margin-bottom:18px}.summary b{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:3px}.summary p{margin:0;color:hsl(var(--ink2))}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.k{background:hsl(var(--card));border:1px solid hsl(var(--line)/.55);border-radius:6px;padding:18px;min-height:142px;display:flex;flex-direction:column}.k.hero{background:linear-gradient(135deg,hsl(var(--accent)),hsl(var(--secondary)))}.k .top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px}.k svg{width:20px;height:20px;stroke:hsl(var(--primary));fill:none;stroke-width:1.75;stroke-linecap:round;stroke-linejoin:round}.k .n{font-size:28px;font-weight:600;letter-spacing:-.04em;font-variant-numeric:tabular-nums;line-height:1.12;margin-top:6px}.k .pills-mini{display:flex;gap:7px;align-items:center;margin-top:auto;padding-top:12px;flex-wrap:wrap}.tag,.chip{font-size:11px;padding:4px 8px;border:1px solid hsl(var(--line));border-radius:5px;background:hsl(var(--secondary));color:hsl(var(--ink2));white-space:nowrap}.tag.v,.s-ok{background:hsl(var(--ok)/.15);border-color:hsl(var(--ok)/.3);color:hsl(var(--ok))}.tag.a,.s-al{background:hsl(var(--warn)/.15);border-color:hsl(var(--warn)/.3);color:hsl(var(--warn))}.tag.r,.s-ru{background:hsl(var(--danger)/.15);border-color:hsl(var(--danger)/.3);color:hsl(var(--danger))}.s-nu{background:hsl(var(--secondary));color:hsl(var(--ink2))}.ver,.b{border:1px solid hsl(var(--line));border-radius:5px;padding:7px 11px;background:hsl(var(--pop));color:hsl(var(--ink));font:inherit;font-size:12px;cursor:pointer;white-space:nowrap}.ver:hover,.b.sec:hover{background:hsl(var(--muted))}.link{background:none;border:0;font:inherit;font-size:12px;color:hsl(var(--primary));cursor:pointer;text-decoration:underline;padding:0}
.section-title{margin:26px 0 12px;display:flex;justify-content:space-between;align-items:end;gap:12px}.section-title h2{font-size:16px;margin:0;font-weight:600}.section-title p{margin:3px 0 0;color:hsl(var(--ink2));font-size:12px}.box{background:hsl(var(--card));border:1px solid hsl(var(--line)/.55);border-radius:6px;padding:18px}.box h3{margin:0 0 4px;font-size:14px;font-weight:600}.box .cab{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;gap:10px}.tog{display:flex;background:hsl(var(--muted)/.6);border-radius:5px;padding:3px}.meter{display:grid;grid-template-columns:minmax(100px,1fr) 120px 110px;align-items:center;gap:12px;margin-top:13px;font-size:12px}.meter i{font-style:normal;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.meter u{display:block;height:6px;border-radius:3px;background:hsl(var(--muted));overflow:hidden}.meter u b{display:block;height:100%;border-radius:3px;width:0;transition:width .9s cubic-bezier(.32,.72,0,1)}.meter s{text-decoration:none;text-align:right;color:hsl(var(--ink2));font-variant-numeric:tabular-nums}.cols{display:flex;align-items:flex-end;gap:4px;height:150px;margin-top:8px}.cols div{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:6px;height:100%}.cols div b{display:block;width:100%;background:hsl(var(--indigo));border-radius:3px 3px 0 0;height:0;transition:height .9s cubic-bezier(.32,.72,0,1)}.cols div em{font-style:normal;font-size:9px;color:hsl(var(--ink2))}.cols div.pico b{background:hsl(var(--primary))}.funil{display:flex;gap:2px;height:30px;margin:8px 0 14px;border-radius:5px;overflow:hidden}.funil span{width:0;transition:width .9s cubic-bezier(.32,.72,0,1)}.leg{display:flex;gap:12px;flex-wrap:wrap;font-size:11px;color:hsl(var(--ink2))}.leg span{display:flex;align-items:center;gap:5px}.leg i{width:7px;height:7px;border-radius:50%;display:inline-block}.impact-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.impact{padding:18px;border:1px solid hsl(var(--line)/.55);background:hsl(var(--card));border-radius:6px}.impact .value{font-size:24px;font-weight:600;letter-spacing:-.03em;margin:8px 0 4px}.impact p{margin:0;color:hsl(var(--ink2));font-size:12px}.esconde .oculta{filter:blur(7px);user-select:none}
.barra{display:grid;grid-template-columns:minmax(230px,1fr) minmax(210px,280px) auto;gap:10px;align-items:start;margin-bottom:10px}.barra>input{width:100%}.multiselect{position:relative}.multiselect summary{list-style:none;border:1px solid hsl(var(--line));border-radius:5px;padding:9px 32px 9px 10px;background:hsl(var(--pop));cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.multiselect summary::-webkit-details-marker{display:none}.multiselect summary:after{content:'⌄';position:absolute;right:11px}.multi-pop{position:absolute;z-index:12;top:calc(100% + 5px);left:0;right:0;background:hsl(var(--pop));border:1px solid hsl(var(--line));border-radius:6px;padding:7px;box-shadow:0 8px 24px hsl(var(--ink)/.12)}.multi-pop label{display:flex;align-items:center;gap:9px;padding:7px;border-radius:5px;cursor:pointer;font-size:12px}.multi-pop label:hover{background:hsl(var(--muted))}.multi-pop button{width:100%;margin-top:4px}.download-note{grid-column:1/-1;color:hsl(var(--ink2));font-size:11px}.notice{display:flex;justify-content:space-between;align-items:center;gap:14px;border:1px solid hsl(var(--warn)/.35);background:hsl(var(--warn)/.1);border-radius:6px;padding:12px 14px;margin:12px 0}.notice b{display:block;font-size:12px}.notice small{color:hsl(var(--ink2))}
table{border-collapse:collapse;width:100%;font-size:12px}th,td{border-bottom:1px solid hsl(var(--line)/.65);padding:10px 12px;text-align:left;white-space:nowrap;max-width:250px;overflow:hidden;text-overflow:ellipsis}th{background:hsl(var(--card));position:sticky;top:0;cursor:pointer;font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:hsl(var(--ink2));font-weight:500}tbody tr{cursor:pointer}tbody tr:hover{background:hsl(var(--ink)/.035)}.wrap{overflow:auto;max-height:62vh;border:1px solid hsl(var(--line));border-radius:6px}.chip{display:inline-block;font-weight:500}.raw{margin-top:12px;border:1px solid hsl(var(--line));border-radius:6px;background:hsl(var(--card))}.raw>summary{cursor:pointer;padding:13px 15px;color:hsl(var(--ink2));font-size:12px}.raw .wrap{border:0;border-top:1px solid hsl(var(--line));border-radius:0;max-height:300px}
button.b{background:hsl(var(--primary));color:hsl(var(--primary-fg));border-color:hsl(var(--primary));padding:9px 14px;font-weight:500}button.b:hover{filter:brightness(1.04)}button.b.sec{background:hsl(var(--pop));color:hsl(var(--ink));border-color:hsl(var(--line))}button.b.r{background:hsl(var(--danger));color:hsl(var(--primary-fg));border-color:hsl(var(--danger))}.wizard{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;counter-reset:step}.step{position:relative;border:1px solid hsl(var(--line)/.65);background:hsl(var(--card));border-radius:6px;padding:18px;padding-top:52px;min-height:210px}.step:before{counter-increment:step;content:counter(step);position:absolute;top:17px;left:18px;width:24px;height:24px;border-radius:5px;display:grid;place-items:center;background:hsl(var(--primary));color:hsl(var(--primary-fg));font-size:12px;font-weight:600}.step h3{font-size:14px;margin:0 0 7px}.step p{font-size:12px;color:hsl(var(--ink2));margin:0 0 12px}.step a{color:hsl(var(--primary));word-break:break-all}.danger-zone{margin-top:18px;padding:18px;border:1px solid hsl(var(--danger)/.3);border-radius:6px;background:hsl(var(--danger)/.07)}.danger-zone h3{margin:0 0 4px;font-size:14px}.danger-zone p{margin:0 0 12px;color:hsl(var(--ink2))}textarea{width:100%;height:100px;font:10px ui-monospace,monospace;padding:10px;border:1px solid hsl(var(--line));border-radius:5px;background:hsl(var(--card));color:hsl(var(--ink))}code{background:hsl(var(--muted));padding:2px 5px;border-radius:5px;font-size:11px}small{color:hsl(var(--ink2))}
dialog{border:1px solid hsl(var(--line));border-radius:8px;padding:0;max-width:600px;width:92vw;background:hsl(var(--pop));color:hsl(var(--ink));box-shadow:0 18px 55px hsl(var(--ink)/.25)}dialog::backdrop{background:hsl(215 25% 14%/.55)}dialog .hd{padding:18px 22px;border-bottom:1px solid hsl(var(--line));display:flex;justify-content:space-between;align-items:center}dialog .bd{padding:6px 22px 22px;max-height:70vh;overflow:auto}dialog h2{margin:0;font-size:18px;font-weight:600}.dtabs{display:flex;gap:3px;flex-wrap:wrap;padding:12px 22px}.busca{display:grid;grid-template-columns:1fr 190px;gap:10px;padding:0 22px 12px}.campo{border:1px solid hsl(var(--line));border-radius:5px;padding:6px 10px}.campo label{display:block;font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:hsl(var(--ink2))}.campo input,.campo select{border:0;padding:3px 0 0;width:100%;font-size:12px;background:none;box-shadow:none}.lista{padding:0 22px;max-height:46vh;overflow:auto}.item{display:flex;align-items:center;gap:12px;border-bottom:1px solid hsl(var(--line));padding:11px 4px;cursor:pointer}.item:hover{background:hsl(var(--ink)/.035)}.item .bola{width:32px;height:32px;border-radius:5px;display:grid;place-items:center;flex:0 0 32px}.item .bola svg{width:16px;height:16px;fill:none;stroke-width:1.75}.item .txt{flex:1;min-width:0}.item .txt small{display:block;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.item .txt b{font-size:12px}.item .seta{color:hsl(var(--ink2));font-size:18px}.rodape{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 22px 0;margin-top:6px;border-top:1px solid hsl(var(--line))}.pag{display:flex;align-items:center;gap:8px;font-size:12px;color:hsl(var(--ink2))}.pag button{border:1px solid hsl(var(--line));background:hsl(var(--pop));border-radius:5px;width:30px;height:30px;cursor:pointer;color:hsl(var(--ink))}.pag button:disabled{opacity:.35}.okbtn{display:block;width:100%;margin:14px 0 0;background:hsl(var(--primary));color:hsl(var(--primary-fg));border:0;border-radius:5px;padding:11px;font:inherit;font-weight:500;cursor:pointer}.okbtn.cinza{background:hsl(var(--secondary));color:hsl(var(--ink2))}.secao{font-size:10px;letter-spacing:.08em;color:hsl(var(--ink2));text-transform:uppercase;margin:18px 0 7px}.secao:first-child{margin-top:6px}.tab2{background:hsl(var(--card));border-radius:6px;overflow:hidden}.tab2 div{display:flex;justify-content:space-between;gap:16px;padding:11px 14px;border-bottom:1px solid hsl(var(--line));font-size:12px}.tab2 div:last-child{border-bottom:0}.tab2 div i{font-style:normal;color:hsl(var(--ink2))}.tab2 div u{text-decoration:none;font-weight:500;text-align:right;word-break:break-word}.vazio{text-align:center;color:hsl(var(--ink2));padding:30px 0;font-size:12px}
@media(max-width:900px){:root{--sb:0px}.sidebar{position:sticky;top:0;width:100%;height:58px;flex-direction:row;border-right:0;border-bottom:1px solid hsl(var(--line));overflow:visible}.sidebar:hover{width:100%}.brand{height:58px;padding:0 12px;border:0}.brand small,.brand span+span{display:none}.sidebar nav{display:flex;margin-left:auto;padding:8px}.sidebar nav button{width:auto;padding:0 9px}.sidebar nav button span:last-child{display:none}header{display:none}main,.sidebar:hover~header+main{margin-left:0;padding:10px}.grid,.wizard{grid-template-columns:1fr 1fr}main>section{padding:18px;min-height:calc(100vh - 78px)}}
@media(max-width:640px){.grid,.impact-grid,.wizard{grid-template-columns:1fr}.pagehead{display:block}.filterbar{align-items:flex-start}.pills{width:100%}.pills button{flex:1;padding:7px 5px}.barra{grid-template-columns:1fr}.download-note{grid-column:auto}.meter{grid-template-columns:1fr 70px}.meter s{display:none}.busca{grid-template-columns:1fr}.wizard .step{min-height:0}.notice{align-items:flex-start;flex-direction:column}main>section{padding:14px}}
.impact-grid{grid-template-columns:repeat(3,1fr)}
.nav-ico{fill:none;stroke:currentColor;stroke-width:1.75;stroke-linecap:round;stroke-linejoin:round}
.definitions{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:0 0 12px}.definitions span{padding:10px 12px;border:1px solid hsl(var(--line)/.65);border-radius:5px;color:hsl(var(--ink2));font-size:11px}.definitions b{display:block;color:hsl(var(--ink));font-size:11px;margin-bottom:2px}.impact .value{margin-bottom:2px}.impact .value-label{color:hsl(var(--ink2));font-size:11px;margin-bottom:14px}.impact dl{margin:0;border-top:1px solid hsl(var(--line)/.65)}.impact dl div{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:9px 0;border-bottom:1px solid hsl(var(--line)/.5)}.impact dl div:last-child{border-bottom:0;padding-bottom:0}.impact dt{color:hsl(var(--ink2));font-size:11px}.impact dd{margin:0;text-align:right;font-size:12px;font-weight:600;font-variant-numeric:tabular-nums}
@media(min-width:901px){:root{--sb:240px;--sb-open:240px}.sidebar,.sidebar:hover{width:240px}.sidebar:hover~header{left:240px}.sidebar:hover~header+main{margin-left:240px}}
@media(max-width:640px){.impact-grid,.grid[style],.definitions{grid-template-columns:1fr!important}}
</style>
<aside class=sidebar>
  <div class=brand><span class=brand-mark>P</span><span><b>Grupo Pomin</b><small>Relatórios AppTicket</small></span></div>
  <nav aria-label="Navegação principal">
    <button data-t=d class=on><svg class=nav-ico viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg><span>Visão executiva</span></button>
    <button data-t=t><svg class=nav-ico viewBox="0 0 24 24"><path d="M7 7h14M17 3l4 4-4 4M17 17H3M7 13l-4 4 4 4"/></svg><span>Transações</span></button>
    <button data-t=c><svg class=nav-ico viewBox="0 0 24 24"><path d="M12 3v12M7 10l5 5 5-5M4 21h16"/></svg><span>Coletar dados</span></button>
  </nav>
</aside>
<header><strong id=crumb>Visão executiva</strong><small id=hint></small><a class=logout href=/logout>Sair</a></header>
<main>

<section id=d class=on>
  <div class=pagehead><div><div class=eyebrow>Evento 36766</div><h1>Visão executiva</h1>
    <p>Receita, conversão e oportunidades não realizadas para orientar decisões comerciais.</p></div></div>
  <div class=filterbar><span class=filter-label>Período analisado</span><div class=pills id=per>
    <button data-p=total class=on>Todo o período</button><button data-p=ontem>Ontem</button>
    <button data-p=hoje>Hoje</button><button data-p=semana>7 dias</button>
    <button data-p=mes>30 dias</button><button data-p=custom>Personalizado</button>
  </div>
  <div class=custom id=cst><input type=date id=de aria-label="Data inicial"> até <input type=date id=ate aria-label="Data final">
    <button class=ver onclick=aplicarCustom()>Aplicar</button></div>
  </div>
  <div class=atualizado id=atu></div>
  <div class=summary><span>◎</span><div><b>Leitura do período</b><p id=resumo></p></div></div>
  <div class=grid id=kpis></div>

  <div class=section-title><div><h2>Onde a receita deixa de acontecer</h2>
    <p>Valores abaixo são oportunidades não convertidas, não prejuízo contábil.</p></div></div>
  <div class=grid style="margin-top:16px;grid-template-columns:1fr 1fr">
    <div class=box><div class=cab><div><h3>Receita por tipo de ingresso</h3><small>Somente compras aprovadas</small></div>
      <div class=tog id=t1><button data-m=rs class=on>R$</button><button data-m=pc>%</button></div></div>
      <div id=g1></div></div>
    <div class=box><div class=cab><div><h3>Não convertido por meio de pagamento</h3><small>Canceladas e expiradas</small></div>
      <div class=tog id=t2><button data-m=pc class=on>%</button><button data-m=rs>R$</button></div></div>
      <div id=g2></div></div>
  </div>

  <div class=grid style="margin-top:16px;grid-template-columns:1fr 1fr">
    <div class=box><div class=cab><div><h3>Compras aprovadas por horário</h3><small>Faixas com maior resposta</small></div><small id=pico></small></div>
      <div class=cols id=g3></div></div>
    <div class=box><h3>Resultado das tentativas qualificadas</h3>
      <div class=funil id=g4></div><div class=leg id=g4l></div>
      <div id=g5 style=margin-top:6px></div></div>
  </div>
  <div class=section-title><div><h2>Composição das vendas, descontos e cortesias</h2>
    <p>Compras, ingressos emitidos e valores concedidos apresentados separadamente.</p></div></div>
  <div class=definitions><span><b>Transação</b>Uma compra aprovada, independentemente da quantidade de ingressos.</span>
    <span><b>Ingresso emitido</b>Um ticket gerado dentro de uma transação.</span>
    <span><b>Valor concedido</b>Soma financeira registrada em <code>value_discount</code>.</span></div>
  <div class=impact-grid id=impacto></div>
</section>

<section id=t>
  <div class=pagehead><div><div class=eyebrow>Base coletada</div><h1>Transações</h1>
    <p>Consulte a base operacional e exporte exatamente o recorte exibido.</p></div></div>
  <div class=barra>
    <input type=text id=q placeholder="Buscar nome, CPF, e-mail ou ID..." oninput=render() aria-label="Buscar transações">
    <details class=multiselect id=fsbox><summary id=fssum>Todos os status</summary><div class=multi-pop id=fsopts></div></details>
    <button class=b onclick=exportaFiltrado()>Baixar dados filtrados</button>
    <small class=download-note>O arquivo baixado contempla somente os filtros e registros visíveis nesta tela.</small>
  </div>
  <div class=atualizado id=cnt></div>
  <div class=notice id=emptyNote hidden><div><b id=emptyTitle></b><small>São iniciações de checkout ainda sem comprador ou ingresso associado. Elas ficam fora dos indicadores e da tabela principal para não distorcer a análise.</small></div><button class=ver id=toggleRaw onclick=toggleVazios()>Mostrar no fim</button></div>
  <div class=wrap><table><thead id=th></thead><tbody id=tb></tbody></table></div>
  <details class=raw id=rawBox hidden><summary id=rawSummary></summary><div class=wrap><table><thead id=rawth></thead><tbody id=rawtb></tbody></table></div></details>
</section>

<section id=c>
  <div class=pagehead><div><div class=eyebrow>Atualização da base</div><h1>Coletar dados</h1>
    <p>Três passos para atualizar o dashboard e a lista de transações.</p></div></div>
  <div class=notice><div><b>Antes de começar, recomendamos apagar a coleta anterior</b><small>Isso evita mistura entre execuções e é a forma mais segura de garantir uma atualização completa.</small></div><button class="b r" onclick=limpar()>Apagar dados atuais</button></div>
  <div class=wizard>
    <article class=step><h3>Abra o painel da AppTicket</h3><p>Entre logado e mantenha esta aplicação aberta em outra aba.</p><a id=lnk href="https://appticket.com.br/areaProdutor/lista/participantes/?ev=36766&origin=new" target=_blank rel=noopener>Abrir página de participantes ↗</a></article>
    <article class=step><h3>Copie o script</h3><p>Use a coleta completa após apagar. Para complementar uma base existente, copie apenas os novos.</p><button class=b onclick=copiar(1)>Copiar coleta completa</button> <button class="b sec" onclick=copiar(0)>Só novos</button><p id=msg aria-live=polite></p></article>
    <article class=step><h3>Cole no Console</h3><p>Na página da AppTicket, pressione <b>F12</b>, abra <b>Console</b>, cole com <b>Ctrl+V</b> e pressione <b>Enter</b>. Os dados voltarão para cá automaticamente.</p></article>
  </div>
  <details class=raw style=margin-top:14px><summary>Ver o script copiado ou usar importação manual</summary><div style="padding:14px"><textarea id=src readonly placeholder="O script aparecerá aqui após copiar."></textarea><p><small>Se a comunicação automática falhar, o navegador baixará <code>coleta.json</code>.</small> <input type=file id=arq accept=.json onchange=importar()></p></div></details>
  <div class=danger-zone><h3>Recomeçar a coleta</h3><p>Apaga permanentemente os dados locais atuais. Recomendado antes de uma nova coleta completa.</p><button class="b r" onclick=limpar()>Apagar dados atuais</button></div>
</section>
</main>

<dialog id=lst>
  <div class=hd><h2>Lista de transacoes</h2><button class=ver onclick=lst.close()>&#10005;</button></div>
  <div class=dtabs id=ltabs></div>
  <div class=atualizado id=latu style="padding:0 24px"></div>
  <div class=busca>
    <div class=campo><label>Buscar transacao</label>
      <input id=lbusca placeholder="Ex.: nome, codigo, valor..." oninput="LP=0;renderLista()"></div>
    <div class=campo><label>Origem</label><select id=lorig onchange="LP=0;renderLista()"></select></div>
  </div>
  <div class=lista id=llista></div>
  <div class=rodape>
    <button class=ver onclick=exportaLista()>Exportar</button>
    <div class=pag><button id=lant onclick="LP--;renderLista()">&#8249;</button>
      <span id=lpag></span><button id=lprox onclick="LP++;renderLista()">&#8250;</button></div>
  </div>
  <div style="padding:0 24px 20px"><button class=okbtn onclick=lst.close()>Ok</button></div>
</dialog>

<dialog id=dlg><div class=hd><h2 id=dlgt></h2><button class=ver onclick=dlg.close()>&#10005;</button></div>
<div class=bd id=dlgb></div></dialog>

<script>
let D={cols:[],rows:[],erros:0},R=[],F=[],ord=null,asc=true,P='total',sig='',oculto=false;
let M1='rs',M2='pc',STATUS_SEL=new Set(),MOSTRA_VAZIOS=false;
const col=k=>D.cols.indexOf(k);
const num=v=>parseFloat(String(v??'').replace(',','.'))||0;
const brl=v=>v.toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const int=v=>v.toLocaleString('pt-BR');
const pct=v=>(v*100).toFixed(2).replace('.',',')+'%';
const esc=s=>String(s??'').replace(/[&<>"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
// rotulo vem do CODIGO, nunca do texto gravado: mudar nome aqui nao exige recoletar
const ST={'1':{n:'Checkout iniciado',c:'s-nu',cor:'hsl(var(--ink2))'},
          '2':{n:'Pendente',c:'s-nu',cor:'hsl(var(--ink2))'},
          '3':{n:'Pagamento expirado',s:'Pix',c:'s-al',cor:'hsl(var(--warn))'},
          '4':{n:'Compra aprovada',c:'s-ok',cor:'hsl(var(--ok))'},
          '5':{n:'Pagamento expirado',s:'Cartão',c:'s-al',cor:'hsl(var(--rose))'},
          '7':{n:'Compra cancelada',c:'s-ru',cor:'hsl(var(--danger))'}};
const st=r=>ST[r[col('status_code')]]||{n:r[col('status')]||'?',c:'s-nu',cor:'hsl(var(--ink2))'};
const CAT=['hsl(var(--primary))','hsl(var(--rose))','hsl(var(--ok))','hsl(var(--warn))','hsl(var(--indigo))'];

const ICO={
 din:'<circle cx=12 cy=12 r=9/><path d="M12 7v10M14.5 9.5h-4a1.7 1.7 0 000 3.4h3a1.7 1.7 0 010 3.4h-4"/>',
 tic:'<path d="M3 9.5V7.5a1 1 0 011-1h16a1 1 0 011 1v2a2.5 2.5 0 000 5v2a1 1 0 01-1 1H4a1 1 0 01-1-1v-2a2.5 2.5 0 000-5z"/><path d="M9 8v8" stroke-dasharray="2 2"/>',
 rel:'<circle cx=12 cy=12 r=9/><path d="M12 7v5l3.2 2"/>',
 chk:'<path d="M3 9.5V7.5a1 1 0 011-1h16a1 1 0 011 1v2a2.5 2.5 0 000 5v2a1 1 0 01-1 1H4a1 1 0 01-1-1v-2a2.5 2.5 0 000-5z"/><path d="M9 12l2 2 4-4"/>',
 xis:'<path d="M3 9.5V7.5a1 1 0 011-1h16a1 1 0 011 1v2a2.5 2.5 0 000 5v2a1 1 0 01-1 1H4a1 1 0 01-1-1v-2a2.5 2.5 0 000-5z"/><path d="M10 10l4 4M14 10l-4 4"/>',
 gra:'<path d="M4 18l4.5-5 3.5 3 4-6 4 4"/><path d="M4 4v16h16"/>',
 car:'<rect x=3 y=6 width=18 height=12 rx=2/><path d="M3 10h18"/>',
 pes:'<circle cx=12 cy=8.5 r=3.2/><path d="M5 19a7 7 0 0114 0"/>'};
const ico=k=>`<svg viewBox="0 0 24 24">${ICO[k]}</svg>`;

document.querySelectorAll('[data-t]').forEach(b=>b.onclick=()=>aba(b.dataset.t));
function aba(t){
  document.querySelectorAll('[data-t]').forEach(x=>x.classList.toggle('on',x.dataset.t==t));
  document.querySelectorAll('section').forEach(s=>s.classList.toggle('on',s.id==t));
  crumb.textContent={d:'Visão executiva',t:'Transações',c:'Coletar dados'}[t];
}
document.getElementById('per').onclick=e=>{const p=e.target.dataset.p;if(!p)return;
  P=p;
  document.querySelectorAll('#per button').forEach(b=>b.classList.toggle('on',b.dataset.p==P));
  document.getElementById('cst').classList.toggle('on',P=='custom');
  if(P!='custom')atualizarPeriodo();};
t1.onclick=e=>{if(!e.target.dataset.m)return;M1=e.target.dataset.m;
  t1.querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.m==M1));sig='';pinta();};
t2.onclick=e=>{if(!e.target.dataset.m)return;M2=e.target.dataset.m;
  t2.querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.m==M2));sig='';pinta();};

const iso=d=>d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
const dia=r=>{const v=String(r[col('data')]||'').trim();let m=v.match(/^(\d{4}-\d{2}-\d{2})/);
  if(m)return m[1];m=v.match(/^(\d{2})\/(\d{2})\/(\d{4})/);return m?m[3]+'-'+m[2]+'-'+m[1]:''};
function noPeriodo(){
  const h=new Date(),hoje=iso(h),d=n=>{const x=new Date(h);x.setDate(x.getDate()-n);return iso(x)};
  if(P=='hoje')return r=>dia(r)==hoje;
  if(P=='ontem')return r=>dia(r)==d(1);
  if(P=='semana')return r=>dia(r)>=d(6)&&dia(r)<=hoje;
  if(P=='mes')return r=>dia(r)>=d(29)&&dia(r)<=hoje;
  if(P=='custom'){const inicio=document.getElementById('de').value,fim=document.getElementById('ate').value;
    return r=>(!inicio||dia(r)>=inicio)&&(!fim||dia(r)<=fim)}
  return ()=>true;
}
function atualizarPeriodo(){sig='';pinta();render()}
function aplicarCustom(){
  const inicio=document.getElementById('de').value,fim=document.getElementById('ate').value;
  if(inicio&&fim&&inicio>fim)return alert('A data inicial não pode ser posterior à data final.');
  atualizarPeriodo();
}

function anima(el,alvo,fmt){
  const t0=performance.now(),dur=650;
  const passo=t=>{const p=Math.min(1,(t-t0)/dur),e=1-Math.pow(1-p,3);
    el.textContent=fmt(alvo*e);if(p<1)requestAnimationFrame(passo)};
  requestAnimationFrame(passo);
}
function cresce(){requestAnimationFrame(()=>document.querySelectorAll('[data-w]').forEach(
  b=>b.style[b.dataset.eixo||'width']=b.dataset.w+'%'))}

function meters(el,pares,modo){
  const tot=pares.reduce((s,p)=>s+p[1],0)||1,max=pares.length?pares[0][1]:1;
  el.innerHTML=pares.map(([k,v],i)=>`<div class=meter><i title="${esc(k)}">${esc(k)}</i>
    <u><b data-w="${Math.max(2,100*v/max).toFixed(1)}" style="background:${CAT[i%5]}"></b></u>
    <s class="${modo=='rs'?'oculta':''}">${modo=='rs'?brl(v):modo=='ct'?v+' transacoes':pct(v/tot)}</s></div>`).join('')
    ||'<small>sem dados no periodo</small>';
}
function grupo(rows,chave,valor){
  const m={};rows.forEach(r=>{const k=r[col(chave)]||'(nao informado)';m[k]=(m[k]||0)+valor(r)});
  return Object.entries(m).sort((a,b)=>b[1]-a[1]);
}

function pinta(){
  F=R.filter(noPeriodo());
  const cod=c=>F.filter(r=>r[col('status_code')]==c);
  const ap=cod('4'),expRows=[...cod('3'),...cod('5')],cancRows=cod('7'),iniRows=cod('1');
  const naoConv=[...expRows,...cancRows],decididas=[...ap,...naoConv],conv=decididas.length?ap.length/decididas.length:0;
  const discKey=['desconto','value_discount'].find(k=>col(k)>=0);
  const normais=discKey?ap.filter(r=>num(r[col(discKey)])===0&&num(r[col('total')])>0):[];
  const comDesc=discKey?ap.filter(r=>num(r[col(discKey)])>0&&num(r[col('total')])>0):[];
  const cortesias=discKey?ap.filter(r=>num(r[col(discKey)])>0&&num(r[col('total')])===0):[];
  const ticketsEmitidos=ap.reduce((s,r)=>s+ +(r[col('qtde_tickets')]||0),0);
  const ticketsCortesia=cortesias.reduce((s,r)=>s+ +(r[col('qtde_tickets')]||0),0);
  const ticketsVendidos=ticketsEmitidos-ticketsCortesia;
  const liq=ap.reduce((s,r)=>s+num(r[col('liquido')]),0);
  const oportunidade=naoConv.reduce((s,r)=>s+num(r[col('total')]),0);
  const cancelado=cancRows.reduce((s,r)=>s+num(r[col('total')]),0);
  const card=(icone,rot,corpo,extra,tags,cls)=>`<div class="k ${cls||''}"><div class=top>${ico(icone)}${extra||''}</div>
    <div class=rot>${rot}</div><div class="n ${cls=='hero'?'oculta':''}">${corpo}</div>
    ${tags?`<div class=pills-mini>${tags}</div>`:''}</div>`;
  const btn=(c,txt)=>`<button class=ver onclick="verStatus('${c}')">${txt||'Ver'}</button>`;
  const hora={};ap.forEach(r=>{const h=String(r[col('data')]||'').slice(11,13);if(h)hora[h]=(hora[h]||0)+1});
  const topo=Object.entries(hora).sort((a,b)=>b[1]-a[1])[0];

  kpis.innerHTML=
   card('din','Receita líquida aprovada',`<span data-n="${liq}" data-f=brl>${brl(liq)}</span>`,
        `<button class=link onclick=esconder()>${oculto?'Mostrar':'Esconder'} valores</button>`,
        `<span class="tag v">${ap.length} aprovações</span>${btn('4','Ver aprovadas')}`,'hero')
  +card('chk','Compras aprovadas',`<span data-n="${ap.length}" data-f=int>${int(ap.length)}</span>`,btn('4'),
        `<span class=tag>transações concluídas</span>`)
  +card('tic','Ingressos vendidos',`<span data-n="${ticketsVendidos}" data-f=int>${int(ticketsVendidos)}</span>`,'',
        `<span class="tag v">${int(ticketsCortesia)} cortesias</span><span class=tag>${int(ticketsEmitidos)} emitidos no total</span>`)
  +card('car','Conversão das tentativas',pct(conv),'',
        `<span class=tag>${ap.length} de ${decididas.length} tentativas decididas</span>`)
  +card('xis','Receita não convertida',`<span data-n="${oportunidade}" data-f=brl class=oculta>${brl(oportunidade)}</span>`,btn('3,5,7','Ver tentativas'),
        `<span class="tag r">${cancRows.length} canceladas · ${brl(cancelado)}</span><span class="tag a">${expRows.length} expiradas</span>`)
  +card('pes','Checkouts sem identificação',`<span data-n="${iniRows.length}" data-f=int>${int(iniRows.length)}</span>`,btn('1','Ver iniciações'),
        `<span class=tag>segregados dos indicadores</span>`);

  meters(g1,grupo(ap,'tipo_ingresso',r=>num(r[col('liquido')])),M1);
  const porPagamento=grupo(naoConv,'pagamento',r=>num(r[col('total')]));
  meters(g2,porPagamento,M2);

  const hmax=Math.max(1,...Object.values(hora));
  g3.innerHTML=Array.from({length:24},(_,h)=>{const k=String(h).padStart(2,'0'),v=hora[k]||0;
    return `<div class="${topo&&topo[0]==k?'pico':''}" title="${k}:00 - ${v} compras">
      <b data-w="${100*v/hmax}" data-eixo=height></b><em>${h%3?'':k}</em></div>`}).join('');
  pico.textContent=topo?`pico as ${topo[0]}:00`:'';

  const fun=[['4',ap.length],['5',cod('5').length],['3',cod('3').length],['7',cancRows.length]]
    .filter(x=>x[1]).sort((a,b)=>b[1]-a[1]);
  const ftot=fun.reduce((s,x)=>s+x[1],0)||1;
  g4.innerHTML=fun.map(([c,v])=>`<span data-w="${100*v/ftot}" style="background:${ST[c].cor}"
    title="${ST[c].n}: ${v}"></span>`).join('');
  g4l.innerHTML=fun.map(([c,v])=>`<span><i style="background:${ST[c].cor}"></i>${ST[c].n}${ST[c].s?' ('+ST[c].s+')':''}: <b>${v}</b></span>`).join('');
  const motivos={};naoConv.forEach(r=>{const s=st(r),p=r[col('pagamento')]||'meio não informado';
    const k=s.n+(s.s?' · '+s.s:'')+' · '+p;motivos[k]=(motivos[k]||0)+1});
  meters(g5,Object.entries(motivos).sort((a,b)=>b[1]-a[1]),'ct');

  const principal=porPagamento[0];
  const somaDesc=comDesc.reduce((s,r)=>s+num(r[col(discKey)]),0);
  const valorCortesia=discKey?cortesias.reduce((s,r)=>s+num(r[col(discKey)]),0):0;
  const ticketsNormais=normais.reduce((s,r)=>s+ +(r[col('qtde_tickets')]||0),0);
  const ticketsCupom=comDesc.reduce((s,r)=>s+ +(r[col('qtde_tickets')]||0),0);
  const linha=(rotulo,valor,oculta=false)=>`<div><dt>${rotulo}</dt><dd class="${oculta?'oculta':''}">${valor}</dd></div>`;
  const impactoCard=(titulo,valor,unidade,linhas)=>`<article class=impact><div class=eyebrow>${titulo}</div>
    <div class=value>${valor}</div><div class=value-label>${unidade}</div><dl>${linhas}</dl></article>`;
  impacto.innerHTML=discKey?
    impactoCard('Sem desconto',int(normais.length),'transações aprovadas',
      linha('Ingressos emitidos',int(ticketsNormais))+linha('Valor concedido',brl(0),true))+
    impactoCard('Com cupom',int(comDesc.length),'transações aprovadas',
      linha('Ingressos emitidos',int(ticketsCupom))+linha('Valor concedido',brl(somaDesc),true)+
      linha('Média por transação',brl(comDesc.length?somaDesc/comDesc.length:0),true))+
    impactoCard('Cortesia 100%',int(ticketsCortesia),'ingressos de cortesia',
      linha('Transações',int(cortesias.length))+linha('Valor concedido',brl(valorCortesia),true)+
      linha('Média por ingresso',brl(ticketsCortesia?valorCortesia/ticketsCortesia:0),true)):
    '<article class=impact style="grid-column:1/-1"><div class=eyebrow>Dados indisponíveis</div><p>O campo value_discount não foi fornecido pela base.</p></article>';
  resumo.textContent=`${ap.length} compras aprovadas resultaram em ${int(ticketsVendidos)} ingressos vendidos e ${int(ticketsCortesia)} cortesias (${int(ticketsEmitidos)} emitidos no total), gerando ${brl(liq)} líquidos. ${naoConv.length?`${naoConv.length} tentativas não converteram ${brl(oportunidade)}${principal?`, com maior concentração em ${principal[0]}`:''}.`:'Não houve cancelamentos ou expirações no período.'}`;

  document.querySelectorAll('[data-n]').forEach(el=>{
    const f=el.dataset.f=='brl'?brl:int;anima(el,+el.dataset.n,v=>f(el.dataset.f=='brl'?v:Math.round(v)));});
  cresce();
  atu.textContent='Atualizado em: '+new Date().toLocaleString('pt-BR')
    +' · '+F.length+' transacoes no periodo';
}
function esconder(){oculto=!oculto;document.body.classList.toggle('esconde',oculto);sig='';pinta()}
function verStatus(cs){abrirLista(cs)}

// ---- modal "Lista de transacoes" ----
const ABAS=[['','Tudo'],['1','Iniciada'],['2','Pendente'],['4','Aprovada'],['7','Cancelada'],['3,5','Expirada']];
let LC='',LP=0,aberto=0;
function abrirLista(cs){
  LC=cs||'';LP=0;lbusca.value='';
  ltabs.innerHTML=ABAS.map(([c,n])=>`<button data-c="${c}" class="${c==LC?'on':''}">${n}</button>`).join('');
  const org=[...new Set(F.map(r=>r[col('origem')]).filter(Boolean))].sort();
  lorig.innerHTML='<option value="">Todos</option>'+org.map(o=>`<option>${esc(o)}</option>`).join('');
  renderLista();lst.showModal();
}
ltabs.onclick=e=>{if(e.target.dataset.c===undefined)return;
  LC=e.target.dataset.c;LP=0;
  ltabs.querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.c==LC));renderLista()};
function filtraLista(){
  const f=lbusca.value.toLowerCase(),o=lorig.value,cs=LC?LC.split(','):null;
  return F.filter(r=>(!cs||cs.includes(r[col('status_code')]))&&(!o||r[col('origem')]==o)
    &&['nome','email','cpf','telefone','id_transacao','total'].map(c=>r[col(c)]).join(' ').toLowerCase().includes(f));
}
const dataCurta=r=>{const d=String(r[col('data')]||'');
  return d?d.slice(8,10)+'/'+d.slice(5,7)+' as '+d.slice(11,16):''};
function renderLista(){
  const rows=filtraLista(),por=10,tot=Math.max(1,Math.ceil(rows.length/por));
  LP=Math.min(Math.max(0,LP),tot-1);
  latu.textContent=rows.length+' transacoes'+(P=='total'?'':' no periodo selecionado');
  llista.innerHTML=rows.slice(LP*por,LP*por+por).map(r=>{const s=st(r);
    return `<div class=item onclick=abrir(${R.indexOf(r)})>
      <span class=bola style="background:${s.cor}22"><svg viewBox="0 0 24 24" stroke="${s.cor}">${ICO.rel}</svg></span>
      <span class=txt><small>${esc(r[col('nome')])} , ${dataCurta(r)}</small>
        <b>${esc(s.n)}${s.s?' · '+s.s:''}</b></span><span class=seta>&#8250;</span></div>`}).join('')
    ||'<div class=vazio>nenhuma transacao com esse filtro</div>';
  lpag.textContent=(LP+1)+' de '+tot;
  lant.disabled=LP<=0;lprox.disabled=LP>=tot-1;
}
function exportaLista(){
  const rows=filtraLista();
  if(!confirm(`O download contempla apenas as ${rows.length} transações filtradas nesta lista. Deseja continuar?`))return;
  baixaCSV(rows,'transacoes-filtradas.csv');
}
function baixaCSV(rows,nome){
  const cs=['id_transacao','data','nome','cpf','email','telefone','cargo','tipo_ingresso','pagamento','total','desconto','liquido','status'];
  const linhas=[cs.join(';')].concat(rows.map(r=>cs.map(c=>{
    const v=c=='status'?st(r).n+(st(r).s?' · '+st(r).s:''):r[col(c)];
    return '"'+String(v??'').replace(/"/g,'""')+'"'}).join(';')));
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob(['\ufeff'+linhas.join('\r\n')],{type:'text/csv'}));
  a.download=nome;a.click();URL.revokeObjectURL(a.href);
}

const MOSTRA=['data','nome','cpf','email','telefone','cargo','tipo_ingresso','pagamento','total','status'];
const checkoutVazio=r=>r[col('status_code')]=='1'&&!['nome','cpf','email','telefone','cargo'].some(k=>r[col(k)]);
function filtraTabela(){
  const f=q.value.toLowerCase();
  return F.filter(r=>(!STATUS_SEL.size||STATUS_SEL.has(String(r[col('status_code')])))&&r.join(' ').toLowerCase().includes(f));
}
function htmlLinha(r){return `<tr onclick=abrir(${R.indexOf(r)})>`+MOSTRA.map(c=>{
    if(c=='status'){const s=st(r);return `<td><span class="chip ${s.c}">${esc(s.n)}${s.s?' · '+s.s:''}</span></td>`}
    const v=r[col(c)];
    if(c=='total')return `<td class=oculta>${v?brl(num(v)):''}</td>`;
    return `<td title="${esc(v)}">${esc(v)}</td>`}).join('')+'</tr>'}
function render(){
  let rows=filtraTabela(),vazios=rows.filter(checkoutVazio);rows=rows.filter(r=>!checkoutVazio(r));
  if(ord!=null){const sort=(a,b)=>String(a[ord]??'').localeCompare(String(b[ord]??''),'pt',{numeric:true})*(asc?1:-1);rows.sort(sort);vazios.sort(sort)}
  const cab='<tr>'+MOSTRA.map(c=>`<th onclick="ordena('${c}')">${c.replace(/_/g,' ')}</th>`).join('')+'</tr>';
  th.innerHTML=cab;rawth.innerHTML=cab;
  tb.innerHTML=rows.map(htmlLinha).join('')||'<tr><td colspan=10><div class=vazio>Nenhuma transação encontrada com estes filtros.</div></td></tr>';
  rawtb.innerHTML=vazios.map(htmlLinha).join('');
  emptyNote.hidden=!vazios.length;rawBox.hidden=!vazios.length;rawBox.open=MOSTRA_VAZIOS&&!!vazios.length;
  emptyTitle.textContent=`${vazios.length} iniciações de checkout sem identificação foram separadas`;
  rawSummary.textContent=`Dados brutos sem identificação (${vazios.length}) — exibidos por último`;
  toggleRaw.textContent=MOSTRA_VAZIOS?'Ocultar dados brutos':'Mostrar no fim';
  cnt.textContent=`${rows.length} registros analisáveis no recorte`+(vazios.length?` · ${vazios.length} iniciações segregadas`:'')+(D.erros?` · ${D.erros} com erro de coleta`:'');
}
function toggleVazios(){MOSTRA_VAZIOS=!MOSTRA_VAZIOS;render();if(MOSTRA_VAZIOS)rawBox.scrollIntoView({behavior:'smooth',block:'start'})}
function mudaStatus(el){el.checked?STATUS_SEL.add(el.value):STATUS_SEL.delete(el.value);fssum.textContent=STATUS_SEL.size?`${STATUS_SEL.size} status selecionado${STATUS_SEL.size>1?'s':''}`:'Todos os status';render()}
function limpaStatus(){STATUS_SEL.clear();fsopts.querySelectorAll('input').forEach(x=>x.checked=false);fssum.textContent='Todos os status';render()}
function exportaFiltrado(){
  let rows=filtraTabela();if(!MOSTRA_VAZIOS)rows=rows.filter(r=>!checkoutVazio(r));
  if(!rows.length)return alert('Não há registros visíveis para baixar. Ajuste os filtros e tente novamente.');
  if(!confirm(`Atenção: o download contempla somente os ${rows.length} registros filtrados e visíveis nesta tela. Deseja continuar?`))return;
  baixaCSV(rows,'transacoes-filtradas.csv');
}
function ordena(c){const i=col(c);asc=ord==i?!asc:true;ord=i;render()}
function abrir(i){
  const r=R[i],s=st(r),g=c=>r[col(c)];
  const ln=(k,v)=>v?`<div><i>${k}</i><u>${v}</u></div>`:'';
  const bloco=(t,html)=>html?`<div class=secao>${t}</div><div class=tab2>${html}</div>`:'';
  dlgt.textContent='Transacao #APP'+g('id_transacao');
  dlgb.innerHTML=
    bloco('Informacoes da compra',
      ln('Valor',g('total')?brl(num(g('total'))):'')
     +ln('Desconto',g('desconto')?brl(num(g('desconto'))):'')
     +ln('Valor liquido',g('liquido')?brl(num(g('liquido'))):'')
     +ln('Origem',esc(g('origem')))
     +ln('Comprador',esc(g('nome')))
     +ln('Data da compra',esc(g('data')))
     +ln('Status da compra',`<span class="chip ${s.c}">${esc(s.n)}${s.s?' · '+s.s:''}</span>`)
     +ln('Status no AppTicket',esc(g('status_api')))
     +ln('ID da compra','#APP'+esc(g('id_transacao')))
     +ln('Pagamento',esc(g('pagamento'))))
   +bloco('Dados do participante',
      ln('CPF',esc(g('cpf')))+ln('E-mail',esc(g('email')))
     +ln('Telefone',esc(g('telefone')))+ln('Cargo',esc(g('cargo'))))
   +bloco('Tickets inclusos nesta compra',
      ln(esc(g('tipo_ingresso'))||'(sem ingresso emitido)',
         g('liquido')?brl(num(g('liquido')))+(g('qtde_tickets')>1?' · '+g('qtde_tickets')+'x':''):'-'))
   +bloco('Diagnostico',ln('Erro na coleta',esc(g('erro'))))
   +'<button class="okbtn cinza" onclick=dlg.close()>Fechar</button>';
  dlg.showModal();
}

async function copiar(tudo){
  const s=await fetch('/coletor.js'+(tudo?'?tudo=1':'')).then(r=>r.text());
  src.value=s;
  try{await navigator.clipboard.writeText(s);msg.textContent=' copiado, cole no console';}
  catch(e){src.select();msg.textContent=' selecione o texto abaixo e copie (Ctrl+C)';}
}
async function importar(){
  const f=arq.files[0];if(!f)return;
  msg.textContent=' '+await (await fetch('/ingest',{method:'POST',body:await f.text()})).text();
  carregar();
}
async function limpar(){
  if(!confirm('Apagar todos os dados coletados neste computador? Esta ação é recomendada antes de uma coleta completa e não pode ser desfeita.'))return;
  await fetch('/limpar',{method:'POST'});sig='';await carregar();alert('Dados apagados. Agora siga os três passos para fazer uma coleta completa e limpa.');
}

async function carregar(){
  if(dlg.open||lst.open)return;            // nao redesenha por baixo de um modal aberto
  D=await (await fetch('/dados')).json();R=D.rows;
  hint.textContent=R.length?R.length+' transações coletadas':'Nenhum dado coletado';
  const novo=R.length+'|'+D.erros;
  if(novo==sig)return;                     // sem dado novo: nao reanima os graficos
  sig=novo;
  const cods=[...new Set(R.map(r=>String(r[col('status_code')])).filter(Boolean))].sort();
  fsopts.innerHTML=cods.map(c=>{const s=ST[c]||{n:'Status '+c};return `<label><input type=checkbox value="${c}" ${STATUS_SEL.has(c)?'checked':''} onchange=mudaStatus(this)> <span>${esc(s.n)}${s.s?' · '+s.s:''}</span></label>`}).join('')
    +'<button class="ver" onclick=limpaStatus()>Limpar seleção</button>';
  pinta();render();
  if(!aberto&&location.hash.startsWith('#lista')){aberto=1;abrirLista(location.hash.split('/')[1]||'')}
  if(!aberto&&location.hash.startsWith('#ficha')){const id=location.hash.split('/')[1];
    const i=R.findIndex(r=>r[col('id_transacao')]==id);if(i>=0){aberto=1;abrir(i)}}
}
carregar();setInterval(carregar,5000);
</script></html>"""


def demo():
    import unittest
    suite = unittest.defaultTestLoader.discover(DIR, pattern="test_*.py")
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    if "test" in sys.argv:
        demo()
