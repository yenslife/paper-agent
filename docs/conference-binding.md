# Conference 綁定邏輯

這份文件說明目前系統如何判斷 `conference`，以及 paper 與 conference entity 的綁定流程。

## 目前的資料模型

- `papers`
  - `conference_id`
  - `venue`
  - `year`
  - `source_page_url`
- `conferences`
  - `name`
  - `normalized_name`
  - `identity_key`
  - `year`
  - `source_page_url`

設計原則是：

- `venue` 仍保留在 `papers` 上，方便相容既有查詢與 UI
- `conferences` 是獨立 entity，方便未來做 conference list、依會議篩 paper、手動管理
- `paper.conference_id` 是正式關聯

## Markdown parse 前的 conference 判斷

在 LLM parser 開始解析 Markdown 前，backend 會先查出目前資料庫裡已有的 conference labels，並把它們塞進 parser prompt。

目前 prompt 的要求是：

- 若某篇 paper 所屬會議可以對上既有 conference label，必須直接沿用完全相同的名字
- 若沒有對到既有 conference label，才建立一個新的簡潔會議名稱，放進 `venue`

這一步的目的不是直接建立資料庫 entity，而是讓 parser 的輸出先盡量 canonicalized，減少：

- `USENIX Security`
- `USENIX Security 2024`
- `USENIX Security '24`
- `USENIX Sec`

這類名稱漂移。

## parser 輸出後的 conference resolve/create

當 parser 產生 `ParsedPaper` 後，ingestion 會在真正寫入 `papers` 之前做一次 conference resolve。

流程如下：

1. 如果 `parsed.venue` 不存在，就不建立 conference entity
2. 若 `parsed.venue` 存在，先把名稱做 normalization
3. 用 `normalized_name + year + source_page_url` 組成 identity
4. 在資料庫裡找可能重複的 conference
5. 找到就重用既有 conference
6. 找不到才建立新的 conference
7. 建立 `paper` 時把 `conference_id` 指向該 conference
8. 同步把 `paper.venue / year / source_page_url` 對齊到 conference 的 canonical 值

## 目前的「重複 conference」判斷方式

目前不是用 embedding，也不是用另一個 LLM 做 fuzzy resolution，而是規則式比對。

### 1. 名稱 normalization

會把 conference 名稱：

- 轉小寫
- 去掉標點
- 非英數字元轉空白
- 合併多餘空白

例如：

- `USENIX Security`
- `USENIX Security '24`
- `usenix-security`

都會先被轉成接近的 normalized form。

### 2. 候選過濾

找重複 conference 時，會先找：

- `normalized_name` 相同

再進一步用以下資訊縮小範圍：

- `year` 相同，或資料庫中的 `year` 為空
- `source_page_url` 相同，或資料庫中的 `source_page_url` 為空

### 3. 排序偏好

若有多個候選，會偏好：

1. `source_page_url` 完全相同
2. `year` 完全相同
3. 名稱排序較前者

所以現在的策略比較接近：

- 先用名稱找同一個 conference family
- 再用 year 與 source page 做 disambiguation

## 前端手動綁定 conference entity

前端的 `Paper records` 區塊有兩個地方可以觸發：

- paper 卡片上的 `綁定 conference 實體`
- 編輯表單中的 `取出並綁定 conference 實體`

這個按鈕會呼叫：

- `POST /papers/{paper_id}/resolve-conference`

backend 會：

1. 若 paper 已經綁過 conference，直接回 `already_attached`
2. 若 paper 還沒綁，但能找到重複 conference，回 `reused_existing`
3. 若 paper 還沒綁且找不到重複 conference，建立新 entity，回 `created_new`
4. 若 paper 缺少 `venue`，回 `unresolved`

前端會顯示：

- 已綁定既有 conference
- 已重用重複 conference，沒有新建
- 已建立新的 conference entity
- 因資訊不足無法建立

## 目前的限制

- 目前的重複 conference 判斷仍是規則式，不是 semantic resolution
- `source_page_url` 很有幫助；若缺少它，主要只能靠 `venue + year`
- 若 parser 產生錯的 `venue`，目前還是可能建立錯的 conference entity
- 尚未提供完整的 conference 管理 UI，例如：
  - merge conferences
  - rename conference
  - conference detail page
  - conference 下的所有 papers 清單

## 下一步建議

若要讓這個功能更穩，下一步建議是：

1. 新增 conference 管理頁
2. 支援手動 merge 兩個 conference entities
3. 在 parser prompt 裡加入更多既有 conference alias 示例
4. 對 `conference` 做更明確的 canonical naming policy
