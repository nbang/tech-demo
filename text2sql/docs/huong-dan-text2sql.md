# Tự xây công cụ Text-to-SQL chạy hoàn toàn nội bộ với LLM mã nguồn mở

> Biến câu hỏi tiếng người thành câu lệnh SQL cho PostgreSQL — dữ liệu và lược đồ không bao giờ rời khỏi máy của bạn.

## Giới thiệu

Trong các bài trước, chúng ta đã cùng tìm hiểu về cơ sở dữ liệu vector và cách chạy LLM cục bộ. Lần này, chúng ta sẽ ghép những mảnh ghép đó lại để giải một bài toán rất thực tế: **làm sao để một người không rành SQL vẫn có thể "hỏi" cơ sở dữ liệu bằng tiếng người?**

Hãy tưởng tượng bạn chỉ cần gõ:

> *"Cho tôi xem người đặt nhiều đơn hàng nhất trong tháng này"*

và hệ thống tự động sinh ra câu SQL chính xác, chạy nó trên database rồi trả về kết quả. Đó chính là **Text-to-SQL**.

Điều khiến bài này khác với việc gọi API của một dịch vụ đám mây nào đó là: **toàn bộ hệ thống chạy nội bộ (self-hosted)**. Chúng ta dùng LLM mã nguồn mở qua [Ollama](https://ollama.com), nên lược đồ database lẫn dữ liệu nhạy cảm không bao giờ bị gửi ra ngoài. Đây là yêu cầu gần như bắt buộc khi làm việc với dữ liệu doanh nghiệp.

Cụ thể, công cụ của chúng ta — đặt tên là `text2sql` — sẽ:

- Kết nối tới PostgreSQL chỉ bằng một **connection string**.
- Tự động trích xuất lược đồ (DDL) và xây một **kho tri thức RAG** từ lược đồ đó.
- Nhận câu hỏi tiếng người, sinh ra câu SQL phù hợp với đúng database này.
- Thực thi câu lệnh và hiển thị kết quả ngay trên giao diện dòng lệnh.

## Kiến trúc tổng quan

Luồng xử lý gồm hai giai đoạn: **nạp lược đồ (ingest)** một lần cho mỗi database, và **hỏi đáp (ask)** lặp lại nhiều lần.

```
                  ┌──────────────┐   DDL    ┌───────────────┐  embeddings  ┌──────────────┐
  connection ───▶ │  introspect  │ ───────▶ │  schema docs  │ ───────────▶ │ vector store │
   string         └──────────────┘          └───────────────┘   (Ollama)   └──────┬───────┘
                                                                                   │ truy hồi top-k
  câu hỏi ─────────────────────────────────────────────────────────────────────▶ │
                                                                            ┌──────▼───────┐
                                                                            │  LLM (Ollama)│ ──▶ SQL ──▶ thực thi ──▶ kết quả
                                                                            └──────────────┘
```

Vì sao lại cần bước RAG (truy hồi) ở đây? Một database thực tế có thể có hàng trăm bảng. Nếu nhồi toàn bộ lược đồ vào prompt thì vừa vượt giới hạn ngữ cảnh, vừa làm "loãng" thông tin khiến mô hình sinh SQL kém chính xác. Thay vào đó, chúng ta **embedding từng bảng**, rồi với mỗi câu hỏi chỉ lấy ra một số bảng liên quan nhất để đưa cho LLM. Đó là tinh thần của schema-RAG.

## Lựa chọn công nghệ

| Thành phần | Lựa chọn | Lý do |
|---|---|---|
| Ngôn ngữ | **Python** | Hệ sinh thái cho database, LLM và RAG đều mạnh nhất ở đây |
| Database | **PostgreSQL** + `psycopg 3` | Phổ biến, có `pg_catalog` để nội suy lược đồ rất chi tiết |
| Mô hình sinh SQL | **qwen3.5:4b** (qua Ollama) | Mô hình instruct mã nguồn mở, nhỏ gọn nhưng suy luận và viết SQL tốt, chạy nội bộ |
| Mô hình embedding | **nomic-embed-text** | Nhẹ, chất lượng tốt, cũng chạy qua Ollama |
| Kho vector | **FAISS** | Thư viện tìm kiếm tương đồng chuẩn mực, khỏi phải "phát minh lại bánh xe" |
| Giao diện | **CLI** (`text2sql`) | Gọn nhẹ, dễ minh hoạ từng bước trong bài |

Một điểm đáng chú ý: với một lược đồ chỉ vài chục bảng, chúng ta không cần một vector database đầy đủ tính năng. [FAISS](https://github.com/facebookresearch/faiss) của Meta cho ta một index dạng "flat" (so khớp toàn bộ) vừa đơn giản, vừa chính xác tuyệt đối, lại được tối ưu sẵn — không cần tự viết phép tính tương đồng.

## Chuẩn bị môi trường

### 1. Cài và khởi động Ollama

```bash
brew install ollama          # hoặc xem hướng dẫn tại ollama.com
ollama serve &               # chạy daemon

# Tải hai mô hình mã nguồn mở
ollama pull qwen3.5:4b       # ~3.4 GB — sinh SQL
ollama pull nomic-embed-text # ~270 MB — sinh embedding
```

### 2. Chuẩn bị PostgreSQL

Trên macOS dùng Homebrew:

```bash
brew install postgresql@18
brew services start postgresql@18
```

### 3. Cài đặt công cụ

```bash
cd text2sql
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env         # tuỳ chỉnh model / chế độ an toàn nếu muốn
```

## Thực hành

### Bước 1 — Trích xuất DDL từ PostgreSQL

Trái tim của bước này là truy vấn vào `pg_catalog` để lấy bảng, cột, kiểu dữ liệu, khoá chính, khoá ngoại và cả **comment** mà người thiết kế database đã ghi. Comment cực kỳ quý: chúng mang ngữ nghĩa nghiệp vụ mà tên cột khô khan không nói hết.

Sau khi nội suy, mỗi bảng được dựng lại thành một câu `CREATE TABLE` — định dạng quen thuộc mà mọi mô hình ngôn ngữ đều "đọc" tốt nhất khi nói về lược đồ database:

```python
def to_ddl(self) -> str:
    """Sinh câu CREATE TABLE — định dạng mà các mô hình text-to-SQL mong đợi."""
    defs = []
    for c in self.columns:
        d = f"{c.name} {c.data_type}"
        if not c.nullable:
            d += " NOT NULL"
        defs.append((d, f" -- {c.comment}" if c.comment else ""))
    if self.primary_key:
        defs.append((f"PRIMARY KEY ({', '.join(self.primary_key)})", ""))
    for fk in self.foreign_keys:
        defs.append((f"FOREIGN KEY ({fk['column']}) "
                     f"REFERENCES {fk['ref_table']}({fk['ref_column']})", ""))
    ...
```

Kết quả thu được cho bảng `orders` trông như sau — chú ý phần comment được giữ nguyên:

```sql
CREATE TABLE public.orders ( -- A purchase placed by a customer; line items live in order_items.
  id integer NOT NULL,
  customer_id integer NOT NULL,
  status text NOT NULL, -- One of: paid, pending, cancelled.
  created_at timestamp with time zone NOT NULL,
  PRIMARY KEY (id),
  FOREIGN KEY (customer_id) REFERENCES customers(id)
);
```

### Bước 2 — Xây dựng schema-RAG

Với mỗi bảng, chúng ta gọi Ollama để sinh embedding cho đoạn DDL đó, rồi lưu vào kho vector. Vì DDL đã chứa cả tên cột lẫn comment nên nó embedding rất "có hồn" cho việc truy hồi.

```python
def embed(text: str) -> list[float]:
    with _client() as c:
        resp = c.post("/api/embeddings",
                      json={"model": settings.embed_model, "prompt": text})
        resp.raise_for_status()
        return resp.json()["embedding"]
```

Phần lưu trữ và tìm kiếm vector, chúng ta giao hẳn cho FAISS. Vì các vector đã được chuẩn hoá L2 nên tích vô hướng (inner product) chính là cosine similarity — chỉ cần dùng `IndexFlatIP`:

```python
@classmethod
def build(cls, ids, documents, vectors):
    embeddings = np.asarray(vectors, dtype=np.float32)
    faiss.normalize_L2(embeddings)
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    return cls(ids, documents, index)

def search(self, query_vector, top_k):
    q = np.asarray([query_vector], dtype=np.float32)
    faiss.normalize_L2(q)
    scores, idx = self.index.search(q, min(top_k, len(self.ids)))
    return [(self.ids[i], self.documents[i], float(s))
            for i, s in zip(idx[0], scores[0]) if i != -1]
```

### Bước 3 — Sinh SQL bằng LLM

Khi nhận câu hỏi, chúng ta embedding câu hỏi đó, truy hồi những bảng liên quan nhất, rồi ghép phần DDL của chúng thành ngữ cảnh cho mô hình. Phần còn lại là một lời nhắc (prompt) gọn gàng: một **system prompt** đặt ra luật chơi, và một **user prompt** chứa lược đồ cùng câu hỏi.

```python
SYSTEM_PROMPT = """You are an expert PostgreSQL analyst. Convert the user's question into ONE valid PostgreSQL query.

Rules:
- Use ONLY the tables and columns in the provided schema. Never invent names.
- Join tables using the documented foreign keys.
- For relative dates ("this month", "today"), use CURRENT_DATE / date_trunc / NOW() — never hardcode dates.
- If a value is not a column (e.g. revenue), derive it from existing columns.

Reply with a JSON object only:
{"sql": "<the query>", "explanation": "<one sentence>", "tables_used": ["schema.table", ...]}"""
```

Chúng ta gọi mô hình qua endpoint hội thoại `/api/chat` của Ollama và yêu cầu nó trả về một đối tượng JSON gồm câu SQL kèm lời giải thích ngắn. Một mẹo nhỏ cho các mô hình "biết suy luận" (như dòng Qwen): bật cờ `think: False` để bỏ qua phần suy luận dài dòng, cho ra câu trả lời trực tiếp và nhanh hơn.

```python
resp = c.post("/api/chat", json={
    "model": settings.gen_model,
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
    "stream": False,
    "think": False,
    "options": {"temperature": 0},
})
```

Cuối cùng, lớp xử lý kết quả "khoan dung" một chút: thử đọc JSON trước, nếu không được thì coi toàn bộ phản hồi là SQL thô. Nhờ vậy công cụ chạy được với nhiều mô hình khác nhau — chỉ cần đổi biến môi trường `TEXT2SQL_GEN_MODEL`.

### Bước 4 — Thực thi và hiển thị kết quả

Câu SQL sau khi sinh ra được chạy bằng `psycopg`. Chúng ta xử lý cẩn thận các kiểu dữ liệu khó tuần tự hoá (Decimal, datetime, UUID…), giới hạn số dòng trả về, và hỗ trợ chế độ **chỉ đọc** để an toàn:

```python
def run_query(connection_string: str, sql: str) -> QueryResult:
    with _connect(connection_string) as conn:
        if settings.read_only:
            conn.read_only = True          # bọc trong transaction READ ONLY
        with conn.cursor() as cur:
            cur.execute(sql)
            if cur.description is None:     # INSERT/UPDATE/DDL...
                conn.commit()
                return QueryResult([], [], cur.rowcount, False)
            columns = [d.name for d in cur.description]
            ...
```

## Chạy thử trên một database mẫu

Chúng ta tạo một database `shop_demo` mô phỏng một cửa hàng nhỏ: `customers`, `products`, `orders`, `order_items`, `payments`. Dữ liệu đơn hàng được neo theo `CURRENT_DATE` để các câu hỏi kiểu "tháng này" luôn có dữ liệu để trả về.

```bash
createdb shop_demo
psql -d shop_demo -f examples/shop_demo.sql
```

Nạp lược đồ và đặt câu hỏi:

```bash
text2sql ingest "postgresql:///shop_demo"
text2sql run "Show me the person who has the most orders this month"
```

Công cụ truy hồi các bảng liên quan (đứng đầu là `orders` và `customers`), rồi mô hình sinh ra:

```sql
SELECT customers.name, COUNT(orders.id) AS order_count
FROM customers
JOIN orders ON customers.id = orders.customer_id
WHERE date_trunc('month', orders.created_at) = date_trunc('month', CURRENT_DATE)
GROUP BY customers.name
ORDER BY order_count DESC
LIMIT 1;
```

Và kết quả thực thi:

```
     name     | order_count
--------------+-------------
 Alice Nguyen |           4
```

Hoàn toàn khớp với dữ liệu mẫu — Alice là người đặt nhiều đơn nhất trong tháng. Lưu ý cách mô hình tự dùng `date_trunc('month', ...)` cho cụm "this month" thay vì hard-code ngày tháng.

Hãy thử một câu khó hơn, đòi hỏi mô hình phải **tự suy ra** công thức tính doanh thu (không có cột `revenue` nào trong lược đồ):

```bash
text2sql run "List the top 3 products by total revenue"
```

```sql
SELECT p.name, SUM(oi.quantity * oi.unit_price) AS total_revenue
FROM order_items oi
JOIN products p ON oi.product_id = p.id
GROUP BY p.name
ORDER BY total_revenue DESC
LIMIT 3;
```

```
        name         | total_revenue
---------------------+---------------
 Standing Desk       |        598.00
 Mechanical Keyboard |        356.00
 Desk Lamp           |        104.70
```

Đây là lúc một mô hình instruct tốt toả sáng: nó đọc DDL, hiểu rằng doanh thu phải tính từ `quantity * unit_price` trong bảng `order_items`, và viết đúng câu JOIN — điều mà một mô hình quá nhỏ thường làm sai.

## Lưu ý khi vận hành

Một vài điểm các bạn nên cân nhắc trước khi dùng thật:

- **Bảo mật connection string.** Khi nạp lược đồ, công cụ lưu connection string (kèm mật khẩu) vào `.text2sql/registry.json` để các lần hỏi sau dùng lại. Thư mục này đã được `.gitignore`, nhưng hãy giữ nó ở nơi an toàn hoặc xoá đi khi dùng xong.
- **Chế độ thực thi.** Mặc định công cụ chạy *mọi* câu SQL được sinh ra, kể cả lệnh ghi. Khi chỉ muốn đọc, hãy bật `TEXT2SQL_READONLY=1` để bọc mọi truy vấn trong transaction `READ ONLY`.
- **Mô hình không phải lúc nào cũng đúng.** LLM có thể sinh SQL sai logic hoặc hiểu nhầm câu hỏi. Đó là lý do công cụ luôn in ra câu SQL để bạn kiểm tra trước khi tin vào kết quả. Mô hình càng lớn (ví dụ `qwen2.5-coder:7b`, `qwen3.5:14b`) thì độ chính xác càng cao.

## Kết luận

Chúng ta vừa xây dựng một công cụ Text-to-SQL hoàn chỉnh, chạy **hoàn toàn nội bộ**: từ việc nội suy lược đồ PostgreSQL, dựng schema-RAG bằng embedding, cho tới sinh và thực thi SQL bằng một LLM mã nguồn mở. Toàn bộ chỉ gói gọn trong vài trăm dòng Python, không phụ thuộc dịch vụ đám mây nào.

Từ nền tảng này, các bạn có thể mở rộng theo nhiều hướng:

- Thử các mô hình khác nhau (`qwen2.5-coder:7b`, `sqlcoder`…) và so sánh độ chính xác.
- Hỗ trợ thêm các hệ quản trị khác như MySQL hay SQL Server.
- Bổ sung "few-shot examples" — vài cặp câu hỏi/SQL mẫu — vào prompt để tăng độ chính xác cho những truy vấn nghiệp vụ đặc thù.
- Thêm vòng tự sửa lỗi: nếu câu SQL chạy lỗi, đưa thông báo lỗi ngược lại cho LLM để nó sửa.

Hy vọng bài viết giúp các bạn có một điểm khởi đầu vững chắc để tự chủ công nghệ Text-to-SQL ngay trên hạ tầng của mình. Chúc các bạn thực hành vui!
