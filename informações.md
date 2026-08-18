voce dever pegar os ID Transação das tabelas dos 2 excels, e começar a fila de execução

- para cada id fazer:

GET /api/transaction/detail/1556344 HTTP/2
Host: apiv2.appticket.com.br
Cookie: appticket_JWT_TOKEN=eyJhbGciOiAiSFMyNTYiLCAidHlwIjogIkpXVCJ9.eyJzdWIiOiAiNGM4ZTYxMTkxOGUwYzFkMDVhMWRmZWY4MWU5YzUzN2YiLCAiaWQiOiAxMTA1NjkwMTIsICJuYW1lIjogIlEyRnRhV3hoSUU5c2FYWmxhWEpoIiwgInRva2VuIjogIiIsICJpYXQiOiAxNzg2OTk3NTcwIH0.45KeHIJv_8HJl9HDOoLC0qF3bRHkfndrdJr7g3-Kxjk; _fbp=fb.2.1786997430507.481376755878890682; _gid=GA1.3.560703101.1786997431; __utma=160191341.180064103.1786997393.1786997431.1786997431.1; __utmc=160191341; __utmz=160191341.1786997431.1.1.utmcsr=(direct)|utmccn=(direct)|utmcmd=(none); __utmb=160191341.1.10.1786997431; _ga=GA1.1.180064103.1786997393; _gcl_au=1.1.600946924.1786997399.1950090051.1786997417.1786997690.38993953.1786997417.1786997690; _ga_HH33W1N0F2=GS2.1.s1786997392$o1$g1$t1786997712$j44$l0$h0; _ga_3CX76491ER=GS2.1.s1786997398$o1$g1$t1786997805$j60$l0$h0; appticket_session=eyJpdiI6IkxlbHRJNmNGQ0dIU2JvZEUwTkJzWkE9PSIsInZhbHVlIjoiZGE1dkE2TjJ6bVM4bkJjL0d3T2hDc0VaZERLaDRyL0VJYzR4RGl1ZHFKRGducGpub3pQUkR0dHR0RzFGRzVKSVo2SlhqUnQ2K1NiK1lyRkp6UlNmVkt1N0EwQWVYT2pJSVRNelNjVGNyRHkzWXNsUW5DbHp2SWtzNWVPTmszTEQiLCJtYWMiOiJiZTM0ZTBjMThmMGI1YjQ4Y2Q2YzdiOWNmNjY5MTcyNTAxNDJjY2E3YTgyZTBkNGM5NTA4MTU0NTZkODJlMzdmIiwidGFnIjoiIn0%3D; XSRF-TOKEN=eyJpdiI6IlRSSE94SzRsM0w5eGpmNHc3YnlTQ1E9PSIsInZhbHVlIjoiKysvaTF2Z1JxeWU0cW1IK1R5TldFcXJjam1Bb09zSjUzcDBGbmVtamVTTW94MVFzSis5dlZtUUE2RGIvdzJyTnVPSVVsQWUzWHhSaTZlMlc2OGIwYjB2YkMzUFRCcHQwUTNjQml0RnB0RVpCTDlVZFBPVms0M3lTbnpzV2xWdngiLCJtYWMiOiIzZmNiNmUzZjgyNjc3ZWYxYmMyNTdlOTE2YzJmNjJhMmRmZmY2NGE4NTNiZTgxZTZkODBlNmYzODUyNDNhZDQ2IiwidGFnIjoiIn0%3D
Sec-Ch-Ua-Platform: "Windows"
X-Xsrf-Token: eyJpdiI6IlRSSE94SzRsM0w5eGpmNHc3YnlTQ1E9PSIsInZhbHVlIjoiKysvaTF2Z1JxeWU0cW1IK1R5TldFcXJjam1Bb09zSjUzcDBGbmVtamVTTW94MVFzSis5dlZtUUE2RGIvdzJyTnVPSVVsQWUzWHhSaTZlMlc2OGIwYjB2YkMzUFRCcHQwUTNjQml0RnB0RVpCTDlVZFBPVms0M3lTbnpzV2xWdngiLCJtYWMiOiIzZmNiNmUzZjgyNjc3ZWYxYmMyNTdlOTE2YzJmNjJhMmRmZmY2NGE4NTNiZTgxZTZkODBlNmYzODUyNDNhZDQ2IiwidGFnIjoiIn0=
Accept-Language: pt-BR,pt;q=0.9
Accept: application/json
Sec-Ch-Ua: "Not;A=Brand";v="8", "Chromium";v="150"
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36
Sec-Ch-Ua-Mobile: ?0
Origin: https://conta.appticket.com.br
Sec-Fetch-Site: same-site
Sec-Fetch-Mode: cors
Sec-Fetch-Dest: empty
Referer: https://conta.appticket.com.br/
Accept-Encoding: gzip, deflate, br
Priority: u=1, i

passando o ID na URL, o resultado é algo como:
{"success":true,"data":{"transaction":{"id_transaction":1556344,"status_transaction":"4","value_total":"997","value_liquid":"927.21","value_discount":0,"origin":"web","date_start":"2026-08-17 15:34:39","form_pay":"Pix","payment_type_id":2,"payment_type":"Pix","id_promoter":null,"promoter":null,"name_user":"Pedro Henrique Ara\u00fajo Senci","email_user":"pedro.senci@bamex.com.br","qtde_ticket":1,"form_pay_normalized":"Pix","status_normalized":"Aprovada","origin_normalized":"appticket.com.br"},"presences":[{"id_presence":4347501,"fk_transaction":1556344,"id_ticket":115246,"id_event":36766,"id_user":110606127,"used":0,"dt_used":null,"value_total":"997.000","value_liquid":"927.210","value_discount":"0.000","discount_category":null,"ticket_id":115246,"product_sector":"Ingresso Mesa","lote":"1","value_ticket":"927.21","rate_ticket":"69.79","split":null,"id_parent":null,"split_quantity":null,"hide_from_reports":0,"id_discount_category":null,"seat_name":null,"seat_row_name":null}],"history":[{"status":"created","description":"transaction created","status_code":null,"dt_created":"2026-08-17 18:34:39"},{"status":"pending","description":"transaction payment","status_code":null,"dt_created":"2026-08-17 18:44:09"}]},"meta":{"timestamp":"2026-08-17T17:47:49-03:00","request_id":"27a35ff5-7405-4c41-b20b-fdfc4b322c15"}}

devemos pegar o id_presence, com esse id_presence, devemos fazer

POST /areaProdutor/lista/participantes/getOrder.php HTTP/2
Host: appticket.com.br
Cookie: PHPSESSID=54a01efe6dbcccb37760519c66e8f99d; appticket_JWT_TOKEN=eyJhbGciOiAiSFMyNTYiLCAidHlwIjogIkpXVCJ9.eyJzdWIiOiAiNGM4ZTYxMTkxOGUwYzFkMDVhMWRmZWY4MWU5YzUzN2YiLCAiaWQiOiAxMTA1NjkwMTIsICJuYW1lIjogIlEyRnRhV3hoSUU5c2FYWmxhWEpoIiwgInRva2VuIjogIiIsICJpYXQiOiAxNzg2OTk3NTcwIH0.45KeHIJv_8HJl9HDOoLC0qF3bRHkfndrdJr7g3-Kxjk; _fbp=fb.2.1786997430507.481376755878890682; _gid=GA1.3.560703101.1786997431; __utma=160191341.180064103.1786997393.1786997431.1786997431.1; __utmc=160191341; __utmz=160191341.1786997431.1.1.utmcsr=(direct)|utmccn=(direct)|utmcmd=(none); __utmb=160191341.1.10.1786997431; _ga=GA1.1.180064103.1786997393; _gcl_au=1.1.600946924.1786997399.1950090051.1786997417.1786997690.38993953.1786997417.1786997690; _ga_HH33W1N0F2=GS2.1.s1786997392$o1$g1$t1786997712$j44$l0$h0; _ga_3CX76491ER=GS2.1.s1786997398$o1$g1$t1786997805$j60$l0$h0; appticket_session=eyJpdiI6ImNCL0xiQ3VpTDJ6Nm5Ydm1wbVpPS2c9PSIsInZhbHVlIjoiQy9tRCtYYlFqakhYdy9sdjlhd1RMZDJMeG9zem8vaDhjWWNDL0J0eVJGWEZoZFNGTmgxbUhiUUhQU2U3TytyWUJHTE1oaE5jVWM3VG9TdnRzNUVWMTA4N3VWU1pkOGEwanR1dXEzeUZPMmlsREQ3ZzBlMVY5dlYxRmhTV2tkbHEiLCJtYWMiOiI5ZDYwZDIyNGVkODI2ODQyYmU0OWUzYmMxZDVmNDliOWMxZWJhMzM0MTdiNmMzZjcwZTdjNDlhODliNmJkMTJjIiwidGFnIjoiIn0%3D; XSRF-TOKEN=eyJpdiI6ImRSSG9xb0l0WHpvY2hKYXoxalczdWc9PSIsInZhbHVlIjoieUhNbHlnNWZtNmRiS1UvMVdYTmV6Y1M3Ry9pMGNuYytTOThLRWp3OGJCMnVMWnNjZFpJRGl1cFVhY2FlbTR3ZW1NQUdFZWYyaVR3UmR0L1ZLUE4xQjA2aEUyblloeDBPeTFZQzlyZ0E4dU9DOVBlQ0g3bzlyblIwVlRSanRFcGgiLCJtYWMiOiI1N2MyYzQwMTkzNTFjYjcxNDIzMzFkZTczZDQyZDBjNzMxNDgyOThlOTkzYTU3YTc5ZjFkYmJkMjRkNWQyYmMwIiwidGFnIjoiIn0%3D; AWSALB=SxqIBVITdww7g0G25gHzy9FUTXtqATp3ndkDMop84S1VQUcDrecBxGoV3VGzmt1g0f7RlTzN3+M8NNodhatg8MhcMt5KzDFALzZupY0FRFvvATHlTh9oM3wgmLwd; AWSALBCORS=SxqIBVITdww7g0G25gHzy9FUTXtqATp3ndkDMop84S1VQUcDrecBxGoV3VGzmt1g0f7RlTzN3+M8NNodhatg8MhcMt5KzDFALzZupY0FRFvvATHlTh9oM3wgmLwd
Content-Length: 11
Sec-Ch-Ua-Platform: "Windows"
Accept-Language: pt-BR,pt;q=0.9
Sec-Ch-Ua: "Not;A=Brand";v="8", "Chromium";v="150"
Sec-Ch-Ua-Mobile: ?0
X-Requested-With: XMLHttpRequest
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36
Accept: */*
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
Origin: https://appticket.com.br
Sec-Fetch-Site: same-origin
Sec-Fetch-Mode: cors
Sec-Fetch-Dest: empty
Referer: https://appticket.com.br/areaProdutor/lista/participantes/?ev=36766&origin=new
Accept-Encoding: gzip, deflate, br
Priority: u=1, i

idp=4340668


passando o idp= como id_presence, vai vir um resultado:

{"status":true,"attendee":[{"id_transaction":"APP1553470","id":"4340668","name":"Alexandre Teodoro de Oliveira","valor":"1.897,00","product_sector":"Ingresso Camarote","email_user":"alexandre.teodoro0701@gmail.com","id_transacao":"APP-QRT7U3UXFQIZA3","id_external":"P-2XHDU9HDTES6S9","extras":[{"id_form_event":"13145","answer":"168.113.618-08"},{"id_form_event":"13146","answer":"(11)99122-7871"},{"id_form_event":"13147","answer":"alexandre.teodoro0701@gmail.com"},{"id_form_event":"13148","answer":"Alian\u00e7a Divergente"},{"id_form_event":"13149","answer":"CFO"}],"url_ticket":"https:\/\/appticket.com.br\/purchase\/global\/pages\/ticket\/view.php?q=WYBKZTGRCCKS8LGYPWGU15534701NDZGKYK9496Y99L35A3&u=4340668"},{"id_transaction":"APP1553470","id":"4340668","name":"Alexandre Teodoro de Oliveira","valor":"1.897,00","product_sector":"Ingresso Camarote","email_user":"alexandre.teodoro0701@gmail.com","id_transacao":"APP-QRT7U3UXFQIZA3","id_external":"P-2XHDU9HDTES6S9","extras":[{"id_form_event":"13145","answer":"168.113.618-08"},{"id_form_event":"13146","answer":"(11)99122-7871"},{"id_form_event":"13147","answer":"alexandre.teodoro0701@gmail.com"},{"id_form_event":"13148","answer":"Alian\u00e7a Divergente"},{"id_form_event":"13149","answer":"CFO"}],"url_ticket":"https:\/\/appticket.com.br\/purchase\/global\/pages\/ticket\/view.php?q=WRYNG6EMZ1LBTG2E43V415534704NPT28X4AXS2CN8EV0RS&u=4340668"},{"id_transaction":"APP1553470","id":"4340668","name":"Alexandre Teodoro de Oliveira","valor":"1.897,00","product_sector":"Ingresso Camarote","email_user":"alexandre.teodoro0701@gmail.com","id_transacao":"APP-QRT7U3UXFQIZA3","id_external":"P-2XHDU9HDTES6S9","extras":[{"id_form_event":"13145","answer":"168.113.618-08"},{"id_form_event":"13146","answer":"(11)99122-7871"},{"id_form_event":"13147","answer":"alexandre.teodoro0701@gmail.com"},{"id_form_event":"13148","answer":"Alian\u00e7a Divergente"},{"id_form_event":"13149","answer":"CFO"}],"url_ticket":"https:\/\/appticket.com.br\/purchase\/global\/pages\/ticket\/view.php?q=74IX5Z55BFK7A0B884K51553470I997U5R3VQCL3LHYHP4D&u=4340668"}]}

devemos pegar o priemiro, o nome: name, valor: "valor", tipo de ingresso "product_sector", email: "email_user", Telefone: aswer do "id_form_event":"13146", cargo: answer do "id_form_event":"13149", CPF: Answer do "id_form_event":"13145"

armazena

fim desse item, proximo item, repetir fluxo

devemos armazenar tudo localmente

e preciso que de uma tela para inicializar isso, de uma para colar os cookies da minha seção, e uma para vizualizar o resultado completo e poder exportar em planilha 