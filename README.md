# myJAMrobot

Bot musical do Telegram.

## Comandos

| Comando | Função |
|---|---|
| `/start` | início |
| `/help` | ajuda |
| `/login` | salva somente o nome de usuário da LAST FM |
| `/playing` | música atual ou última reprodução |
| `/canvas` | Canvas da música, com fallback para a capa |
| `/story` | vídeo Canvas com áudio quando disponível; fallback estático 1080×1920 |
| `/radio` | busca e envia música sem conta vinculada |
| `/lyrics` | card imediato, busca em segundo plano e edição da mesma mensagem com trecho curto |



## Login

`/login <entrada>` aceita exatamente:

- `username`
- `@username`
- `last.fm/username`

A entrada é normalizada e somente `username` é persistido em `lastfm_profiles`. Não há senha, OAuth, callback ou token de usuário. A leitura musical usa o método público [`user.getRecentTracks`](https://www.last.fm/api/show/user.getRecentTracks), que não exige autenticação da conta do usuário; a chave de API pertence apenas à aplicação.
O nome deve seguir a regra atual da [LAST FM](https://www.last.fm/join): 2–15 caracteres, começar por letra e conter apenas letras, números, `_` ou `-`.

## Capas e mídia

- A maior imagem declarada pelas fontes é escolhida; Deezer XL (quando corresponde à faixa), Spotify e a imagem da LAST FM são comparados.
- Não há aumento generativo ou fabricação de detalhe. O cache reutiliza `file_id` do Telegram sem trocar a imagem-fonte.
- Downloads locais aceitam apenas HTTPS e hosts previstos, validam cada redirecionamento, tipo MIME e tamanho máximo.
- O resolver público de Canvas recebe somente o ID público da faixa Spotify; nunca recebe usuário da LAST FM, token de usuário ou dados do Telegram. Defina `MYJAM_SPOTIFY_CANVAS_ENABLED=false` para desativá-lo.
- `/story` produz 1080×1920. Tenta Canvas com prévia de áudio, depois Canvas sem áudio, depois card estático e, por fim, a capa original.

## Letras

`/lyrics` envia o card imediatamente com estado de busca. Uma fila limitada mantém referência forte à tarefa; quando a busca termina, o bot edita a mesma mensagem.

O extrator prioriza seção marcada como refrão, depois estrofe repetida e depois linha repetida. Quando não existe evidência suficiente de refrão, o fallback é identificado apenas como “Trecho curto”, sem alegação falsa. O limite absoluto é **10 palavras**. A letra completa existe apenas na memória durante a seleção e nunca é gravada; o banco guarda somente o trecho final ou um cache negativo curto. Veja [LEGAL_NOTES.md](LEGAL_NOTES.md).

## Rich Messages 2026

O projeto usa `aiogram==3.30.0` e `InputRichMessage` para cabeçalhos, tabelas, mídia, citações e rodapés. Se a API rejeitar um Rich Message, há fallback HTML/foto sem interromper o comando.


## Configuração


```boa sorte

```

@tigrao
