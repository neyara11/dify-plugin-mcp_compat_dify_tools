# MCP Compatible Dify Tools

Extension-плагин для Dify, который отдаёт ваши Dify-**инструменты** как [MCP](https://modelcontextprotocol.io)-сервер. Отметьте нужные тулы на endpoint'е — каждый станет MCP-инструментом, а его входная схема сгенерируется автоматически. Без обёрток-воркфлоу и без ручного описания схем.

Исходный код: https://github.com/neyara11/dify-plugin-mcp_compat_dify_tools

English version: [README.md](../README.md)

## Зачем

Обычно инструмент в Dify публикуется через воркфлоу-обёртку и публикацию приложения — даже когда тул самодостаточен и у него просто много входных параметров. Этот плагин убирает лишний слой: Dify-тул с богатой параметризацией превращается в MCP-тул с ровно такой же параметризацией, и внешние MCP-клиенты (Cherry Studio, Cursor, Roo Code, Kilo Code, Claude Desktop, Cline, LobeChat) вызывают его напрямую.

## Требования

- Dify **1.2.0+**

## Как параметры попадают в схему

| Параметр Dify-тула | В MCP input schema |
|---------------------|---------------------|
| Параметр формы `llm` | Попадает со своим типом, описанием и `enum` для select-опций |
| Settings-параметр **без** значения в конфиге endpoint'а | Попадает — клиент передаёт его при каждом вызове |
| Settings-параметр **со** значением в конфиге endpoint'а | Скрыт и зафиксирован — подставляется автоматически |
| Параметр file/files | Не попадает (в MCP нет типа файла) — передавайте URL файла строкой |

Аргументы вызова перекрывают значения, зафиксированные в конфиге endpoint'а. Если несколько тулов имеют одинаковое имя, последний переименовывается с префиксом провайдера — имена MCP-тулов остаются уникальными.

## Транспорты

| URL | Транспорт | Использование |
|-----|-----------|---------------|
| `.../mcp` | Streamable HTTP | Рекомендуется, современные MCP-клиенты |
| `.../sse` + `.../messages/` | HTTP с SSE (устаревший) | Только для старых клиентов |

## Настройка

### 1. Создайте endpoint и добавьте список тулов

![add_endpoint](../_assets/add_endpoint.png)

![add_tool_list](../_assets/add_tool_list.png)

![edit_tool](../_assets/edit_tool.png)

![save_endpoint](../_assets/save_endpoint.png)

> **Примечание:** изменение списка тулов у уже существующего endpoint'а вступает в силу только после его отключения и повторного включения.

### 2. Скопируйте URL endpoint'а в MCP-клиент

![mcp_urls](../_assets/mcp_urls.png)

**Вариант 1 (рекомендуется): Streamable HTTP**

![mcp_streamable_http_url](../_assets/mcp_streamable_http_url.png)

Пример конфига клиента (Roo Code требует явный `type` для URL-серверов):

```json
{
  "mcpServers": {
    "dify-tools": {
      "type": "streamable-http",
      "url": "https://your-dify-host/e/your-endpoint-id/mcp"
    }
  }
}
```

**Вариант 2: устаревший HTTP с SSE**

![mcp_sse_url](../_assets/mcp_sse_url.png)

```json
{
  "mcpServers": {
    "dify-tools": {
      "type": "sse",
      "url": "https://your-dify-host/e/your-endpoint-id/sse"
    }
  }
}
```

## Аутентификация

Необязательная настройка endpoint'а **Auth token** защищает все URL. Если она задана, каждый запрос должен передавать токен одним из способов:

- заголовок `Authorization: Bearer <token>` (в большинстве клиентов — через `headers`)
- заголовок `X-Api-Key: <token>`
- query-параметр `?token=<token>` (удобно для SSE-клиентов, принимающих только URL)

```json
{
  "mcpServers": {
    "dify-tools": {
      "type": "streamable-http",
      "url": "https://your-dify-host/e/your-endpoint-id/mcp?token=your-token",
      "headers": { "Authorization": "Bearer your-token" }
    }
  }
}
```

## Изменения в этом форке

На основе [junjiem/mcp_compat_dify_tools](https://github.com/junjiem/dify-plugin-mcp_compat_dify_tools) 0.1.1. Исправлено:

- 0.2.1: `tools/list` больше не падает из-за неполных конфигов тулов — отсутствующие `type`/`tool_label` получают значения по умолчанию, сломанные схемы параметров пропускаются с записью в лог сервера, а не роняют весь список; полные трейсбеки ошибок `tools/list`/`tools/call` пишутся в лог сервера.
- 0.2.0: удалён debug-вывод, который печатался поверх JSON-ответа и ломал `tools/call` в plugin daemon ([#7](https://github.com/junjiem/dify-plugin-mcp_compat_dify_tools/issues/7), [#9](https://github.com/junjiem/dify-plugin-mcp_compat_dify_tools/issues/9)).
- Версия протокола теперь согласуется с клиентом (эхо `2024-11-05`, `2025-03-26`, `2025-06-18`, `2025-11-25`) вместо жёстко заданной `2024-11-05`.
- `select`-параметры отдаются как `string` с `enum` — раньше в схему попадал невалидный для JSON Schema тип `select`, из-за чего строгие клиенты отвергали инструменты.
- Незаданные settings-параметры теперь можно передавать при вызове ([#12](https://github.com/junjiem/dify-plugin-mcp_compat_dify_tools/issues/12)).
- Необязательная настройка endpoint'а `auth_token` (Bearer / `X-Api-Key` / `?token=`).
- Ошибки исполнения тула возвращаются как `isError: true` с текстом ошибки — вызывающая LLM видит причину; неизвестное имя тула — JSON-RPC `-32602`.
- Добавлены `ping` и корректная обработка `notifications/*` (202 с пустым телом).
- Исправлен `GET /mcp`: тело ответа было некорректным (dict передавался в Response как iterable).
- Имена MCP-тулов делаются уникальными при совпадениях.
- Общая логика endpoint'ов вынесена в `mcp_common.py`.

Не исправлено (вне зоны ответственности плагина): баги отображения URL в ядре Dify ([#1](https://github.com/junjiem/dify-plugin-mcp_compat_dify_tools/issues/1) — лишняя `}`, [#14](https://github.com/junjiem/dify-plugin-mcp_compat_dify_tools/issues/14) — `localhost` в сгенерированном URL) — они зависят от конфигурации инстанса Dify, а не от плагина.

## Происхождение кода

Форк [junjiem/dify-plugin-mcp_compat_dify_tools](https://github.com/junjiem/dify-plugin-mcp_compat_dify_tools) (открытый исходный код, в апстриме нет файла лицензии), созданного с использованием [hjlarry/dify-plugin-mcp_server](https://github.com/hjlarry/dify-plugin-mcp_server) как референса. Вся заслуга оригинальной архитектуры — у авторов апстрима; этот форк добавляет исправления, перечисленные выше.

## Установка

**Из файла .difypkg:** соберите пакет командой `dify plugin package .` и загрузите его на странице управления плагинами Dify.

**Через GitHub:** на странице управления плагинами выберите установку через GitHub, укажите адрес репозитория, версию и файл пакета.

![install_plugin_via_github](../_assets/install_plugin_via_github.png)

### FAQ: «plugin verification has been enabled, and the plugin ... has a bad signature»

Добавьте `FORCE_VERIFYING_SIGNATURE=false` в конец файла `.env` и перезапустите Dify. Это разрешит установку плагинов, отсутствующих (и, следовательно, непроверенных) в Dify Marketplace — используйте на свой риск.

### FAQ: офлайн-установка

Для настоящего офлайн-пакета (зависимости в комплекте, интернет не нужен) см. [junjiem/dify-plugin-repackaging](https://github.com/junjiem/dify-plugin-repackaging).

### FAQ: клиент подключается, но вызов тула падает

- Убедитесь, что URL соответствует транспорту: `.../mcp` с `type: "streamable-http"`, `.../sse` с `type: "sse"`.
- Roo Code требует явный `type` для URL-серверов; Kilo Code определяет транспорт автоматически.
- Если задан `auth_token` — передавайте его в заголовке или через `?token=`: иначе запросы отклоняются с 401.

### FAQ: окно настроек тула открывается затемнённым за панелью endpoint'а

Это известный баг веб-интерфейса Dify (наложение z-index у вложенных модалок в процессе миграции overlay-компонентов, см. [langgenius/dify#33574](https://github.com/langgenius/dify/issues/33574) и [langgenius/dify#34803](https://github.com/langgenius/dify/issues/34803)), а не баг плагина. Исправления вошли в Dify после версии 1.13.3 — обновите инстанс.

Обходные пути без обновления:
- Диалог необязателен: включённые тулы отдаются в MCP и без индивидуальной настройки. Оставьте значения settings пустыми и передавайте их при вызове как аргументы MCP — незаданные settings-параметры попадают во входную схему.
- Временный хак: откройте DevTools консоль браузера, когда затемнённый диалог появился, и поднимите его слой: `document.querySelectorAll('[role="dialog"], .fixed').forEach(el => el.style.zIndex = 10000)`
