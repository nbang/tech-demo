# Tự xây công cụ Text-to-SPARQL truy vấn đồ thị tri thức bằng LLM mã nguồn mở

> Biến câu hỏi ngôn ngữ tự nhiên thành truy vấn SPARQL cho dữ liệu RDF / knowledge graph — quy chuẩn (ontology) và dữ liệu không bao giờ rời khỏi máy của bạn.

## Giới thiệu

Dữ liệu của thế giới thực không phải lúc nào cũng nằm gọn trong các bảng quan hệ. Rất nhiều tri thức được biểu diễn dưới dạng **đồ thị tri thức (knowledge graph)** bằng RDF (Resource Description Framework) — từ Wikidata, DBpedia cho tới các kho dữ liệu doanh nghiệp — và được truy vấn bằng **SPARQL** (ngôn ngữ truy vấn cho RDF). Nhưng SPARQL có cú pháp riêng, lại đòi hỏi nắm rõ quy chuẩn — các lớp, thuộc tính, namespace — của đồ thị. Làm sao để một người không rành SPARQL vẫn có thể "hỏi" đồ thị bằng ngôn ngữ tự nhiên?

Hãy tưởng tượng bạn chỉ cần gõ:

> *"Khách hàng nào đặt nhiều đơn hàng nhất?"*

và hệ thống tự sinh ra câu SPARQL chính xác, chạy nó trên đồ thị rồi trả về kết quả. Đó chính là **Text-to-SPARQL**.

Điểm đáng chú ý là **toàn bộ hệ thống chạy nội bộ (self-hosted)**: dùng LLM (Large Language Model) mã nguồn mở qua [Ollama](https://ollama.com), nên quy chuẩn lẫn dữ liệu nhạy cảm không bao giờ bị gửi ra ngoài — gần như là yêu cầu bắt buộc khi làm việc với dữ liệu doanh nghiệp.

Công cụ của chúng ta — đặt tên là `text2sparql` — sẽ:

- Kết nối tới một **tệp RDF** (Turtle, RDF/XML…) hoặc một **SPARQL endpoint** từ xa.
- Tự động **trích xuất ontology** (các lớp và thuộc tính) và **rút vài bộ ba mẫu thật** từ đồ thị.
- Đưa cả ontology lẫn dữ liệu mẫu vào prompt, sinh ra câu SPARQL phù hợp với đúng đồ thị này.
- Thực thi truy vấn và hiển thị kết quả.

## Vì sao SPARQL "khó" hơn SQL một chút?

Trong SQL, lược đồ rất tường minh: có bảng, có cột, có khoá ngoại ghi rõ ràng. Còn RDF thì "phẳng" — tất cả chỉ là các bộ ba `(chủ thể, vị từ, đối tượng)`. Không có khái niệm "bảng" hay "cột" được khai báo sẵn; cấu trúc nằm ẩn trong chính dữ liệu.

Vì vậy bước **trích xuất ontology** ở đây không đọc một bảng metadata có sẵn như `pg_catalog`, mà phải **suy ra cấu trúc từ dữ liệu**: có những lớp (class) nào, mỗi lớp thường đi với những thuộc tính (predicate) nào, và giá trị của thuộc tính là chuỗi/số (literal) hay trỏ tới một lớp khác (object). Đây chính là điểm thú vị nhất của bài.

## Kiến trúc tổng quan

Luồng xử lý gồm hai giai đoạn: **nạp ontology (ingest)** một lần cho mỗi đồ thị, và **hỏi đáp (ask)** lặp lại nhiều lần.

```
  tệp RDF /        ┌──────────────┐  lớp + hình dạng thuộc tính
  endpoint  ──────▶│  introspect  │  + vài BỘ BA MẪU THẬT ─────┐
                   └──────────────┘                            │
                                                               ▼
                                          ┌─────────────────────────────────────┐
  câu hỏi ───────────────────────────────▶│  prompt = TOÀN BỘ ontology          │
                                          │  + dữ liệu mẫu THẬT + câu hỏi        │
                                          └──────────────────┬──────────────────┘
                                                             ▼
                                            LLM ─▶ SPARQL ─▶ thực thi ─▶ kết quả
```

## Lựa chọn công nghệ

| Thành phần | Lựa chọn | Lý do |
|---|---|---|
| Ngôn ngữ | **Python** | Hệ sinh thái RDF và LLM đều mạnh |
| Dữ liệu | **RDF** + `rdflib` | Thư viện chuẩn mực, đọc được mọi định dạng và chạy SPARQL ngay trong bộ nhớ |
| Truy vấn từ xa | **SPARQLStore** | Cùng một lớp `rdflib.Graph` cũng nói chuyện được với endpoint từ xa |
| Mô hình sinh SPARQL | **gemma4:31b** (Ollama) | Mô hình instruct ~30B chạy nội bộ, đủ giỏi cho property path và "join" giữa các lớp |
| Giao diện | **CLI** | Gọn nhẹ, dễ minh hoạ và dễ chấm điểm tự động (`eval`) |

Một điểm hay của `rdflib`: dù nguồn là tệp Turtle cục bộ hay một SPARQL endpoint từ xa, ta đều bọc trong cùng một đối tượng `Graph`, nên các truy vấn nội suy và thực thi viết một lần chạy cho cả hai.

## Chuẩn bị môi trường

### 1. Cài và khởi động Ollama

```bash
brew install ollama            
ollama pull gemma4:31b  # sử dụng gemma4 vừa đủ cho môi trường nội bộ
ollama serve &
```

> Không cần mô hình embedding: ontology được đưa thẳng vào prompt nên không có bước vector nào.
> Máy yếu hơn có thể thử một mô hình nhỏ hơn, nhưng độ chính xác giảm rõ (xem phần *Đo độ chính xác*),
> hoặc trỏ `TEXT2SPARQL_GEN_*` sang một endpoint OpenAI-compatible.

### 2. Cài đặt công cụ

```bash
cd text2sparql
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env           # tuỳ chỉnh model / chế độ an toàn nếu muốn
```

## Thực hành

### Bước 1 — Trích xuất ontology từ RDF

Vì RDF không có "lược đồ" tường minh, ta phải **suy ra** nó bằng chính SPARQL. Đầu tiên, tìm tất cả các lớp — vừa các lớp được khai báo (`owl:Class`), vừa các lớp thực sự có thực thể (`?s a ?cls`). Ta cũng lọc bỏ các từ vựng meta (rdf, rdfs, owl, xsd) vì chúng định nghĩa *ngôn ngữ* ontology chứ không phải *nghiệp vụ*:

```python
class_q = f"""
SELECT DISTINCT ?cls WHERE {{
  {{ ?cls a <{OWL.Class}> }} UNION {{ ?cls a <{RDFS.Class}> }} UNION {{ ?s a ?cls }}
  FILTER(isIRI(?cls))
  {meta_filter}        # loại bỏ rdf:/rdfs:/owl:/xsd:
}} LIMIT {settings.max_classes}
"""
```

Tiếp theo, với mỗi lớp, ta tìm những vị từ (predicate) thường xuất hiện trên thực thể của nó, và xem giá trị là kiểu dữ liệu gì hay trỏ tới lớp nào — đây chính là "hình dạng" (shape) của lớp:

```python
prop_q = f"""
SELECT DISTINCT ?p ?dt ?otype WHERE {{
  ?s a <{iri}> ; ?p ?o .
  OPTIONAL {{ ?o a ?otype }}      # nếu đối tượng là một thực thể có kiểu
  BIND(DATATYPE(?o) AS ?dt)       # nếu đối tượng là literal
}} LIMIT {settings.sample_limit}
"""
```

Ngoài ra, ta còn lấy thêm **cây phân cấp lớp** qua `rdfs:subClassOf` — đây chính là thứ làm nên "đồ thị" mà SQL khó diễn đạt. Nhờ vậy tài liệu của mỗi lớp ghi rõ nó là lớp con của ai và có những lớp con nào:

```python
sup_q = f"SELECT DISTINCT ?sup WHERE {{ <{iri}> <{RDFS.subClassOf}> ?sup . FILTER(isIRI(?sup)) }}"
for r in gs.query(sup_q):
    info.super_classes.append(gs.curie(str(r[0])))
```

Nếu đồ thị có khai báo `rdfs:label`/`rdfs:comment` thì ta lấy luôn — chúng mang ngữ nghĩa nghiệp vụ quý giá, như comment mô tả cột/bảng trong CSDL. Còn nếu đồ thị chỉ là **dữ liệu thuần** (như hai đồ thị mẫu ở đây, dùng từ vựng chuẩn schema.org và W3C Org), mô hình dựa vào chính **tên thuật ngữ chuẩn** cộng với dữ liệu mẫu — không bắt buộc phải có ontology mô tả.

Kết quả nội suy cho lớp `schema:Order` được dựng thành một "tài liệu" gọn gàng — đây chính là phần lược đồ ta đưa vào prompt:

```
Class: schema:Order
Instances: 10
Properties (predicate -> range):
  - schema:customer -> schema:Person
  - schema:orderStatus -> xsd:string
  - schema:orderDate -> xsd:dateTime
  - schema:orderedItem -> schema:OrderItem
```

Chú ý: `schema:customer -> schema:Person` cho mô hình biết đây là một liên kết tới lớp khác — tương đương "khoá ngoại" trong thế giới SQL, và là manh mối để mô hình biết cách "join" giữa các lớp.

### Bước 2 — Nạp ontology (ingest)

Vì ontology nhỏ, ta **không cần** embedding, kho vector hay bước truy hồi nào cả. `ingest` chỉ chạy phần nội suy ở Bước 1 đúng một lần, rồi **lưu lại** (danh sách lớp + tài liệu mô tả + bảng prefix) vào một tệp registry JSON, để bước hỏi đáp khỏi phải nội suy lại:

```python
reg[graph_id] = {
    "source": source,
    "classes": ids,
    "documents": documents,   # tài liệu mô tả từng lớp (Bước 1)
    "prefixes": prefixes,
}
```
### Bước 3 — Sinh SPARQL bằng LLM

Khi nhận câu hỏi, ta ghép **toàn bộ quy tắc** đã nạp cùng câu hỏi thành prompt. Một điểm khác biệt quan trọng so với SQL: SPARQL bắt buộc khai báo **PREFIX** cho mọi namespace. Vì vậy ta đưa sẵn **bảng prefix** vào prompt để mô hình viết CURIE (ví dụ `schema:Order`) thay vì dán nguyên IRI dài loằng ngoằng.

**Chỉ đưa lược đồ thôi là chưa đủ.** Đây là bài học quan trọng nhất khi làm Text-to-SPARQL: nếu prompt chỉ có mô tả lớp/thuộc tính ở mức trừu tượng, mô hình **không hình dung được dữ liệu thật trông như thế nào** — nó không biết IRI thật của "Tom Becker" là gì (và thường bịa ra `ex:TomBecker`), không biết các thực thể nối với nhau ra sao, nên viết sai các truy vấn bắc cầu. Thực nghiệm với `qwen3.5:4b` cho thấy: chỉ với lược đồ, câu hỏi *"Tom báo cáo cho ai?"* sinh ra IRI bịa và trả về rỗng.

Giải pháp là **đưa kèm dữ liệu mẫu thật** — vài bộ ba RDF rút trực tiếp từ đồ thị. Mô hình lập tức "thấy" được IRI thật, thuộc tính tên nào đang dùng, và — quan trọng nhất — cách các thực thể móc nối với nhau:

```python
user_prompt = (
    f"# Prefixes available:\n{prefix_table}\n\n"
    f"# Ontology (classes + property shapes):\n{context}\n\n"
    f"# Example instance data (REAL triples):\n{examples}\n\n"   # ← phần grounding
    f"# Question: {question}"
)
```

Khối `examples` được lấy bằng một truy vấn nhỏ trên chính đồ thị, gom vài thực thể mẫu của mỗi lớp:

```python
def sample_triples(source, class_iris, max_subjects=12, per_class=2):
    gs = GraphSource(source)
    for iri in class_iris:
        # ORDER BY ?s để mẫu ổn định giữa các lần chạy (LIMIT không kèm sắp xếp sẽ
        # tuỳ tiện, khiến việc sinh truy vấn — và do đó cả eval — chập chờn).
        for s in gs.query(f"SELECT DISTINCT ?s WHERE {{ ?s a <{iri}> }} ORDER BY ?s LIMIT {per_class}"):
            # ... gom mọi bộ ba của ?s, in ra dạng Turtle với CURIE
```

Kết quả là mô hình nhìn thấy đúng "hình dạng" dữ liệu, ví dụ:

```turtle
ex:raj  a org:Manager, org:Employee, org:Person, org:Agent ;
  schema:name "Raj Patel" ; org:reportsTo ex:sofia ; org:hasSkill ex:python, ex:ml .
ex:python  a org:Skill ; schema:name "Python" ; skos:broader ex:programming .
ex:sf  a gn:City, gn:Place ; schema:name "San Francisco" ; gn:locatedIn ex:usa .
```

Chỉ với vài dòng này, mô hình suy ra được: tìm người theo `schema:name`, đi chuỗi `reportsTo` để leo lên cấp trên, và kỹ năng nối nhau qua `skos:broader`. Sau khi thêm dữ liệu mẫu, đúng câu hỏi *"Tom báo cáo cho ai?"* sinh ra `?p schema:name "Tom Becker" ; org:reportsTo+ ?boss` và trả về chính xác Mei → Raj → Sofia.

> **Vì sao dùng `schema:name` cho tên?** Thay vì tự bịa một thuộc tính riêng (như `org:name`), ta dùng đúng thuật ngữ của một **từ vựng chuẩn** — `schema:name` của schema.org. Đây là thuộc tính tên mà hầu hết LLM "đoán" tới đầu tiên, nên mô hình hiếm khi viết nhầm. Bài học: hãy mô hình hoá dữ liệu theo quy ước phổ biến nhất có thể, để cái mô hình *đoán* trùng đúng với cái dữ liệu *thật sự* dùng.

Lớp xử lý kết quả được viết "khoan dung": thử parse JSON `{"sparql": ...}` trước, nếu không được thì coi toàn bộ phản hồi là SPARQL thô và cắt gọn phần thừa. Nhờ vậy công cụ chạy được với nhiều loại mô hình mà không cần đổi code — chỉ cần đổi biến `TEXT2SPARQL_GEN_MODEL`.

Một lưu ý với các mô hình **suy luận (reasoning)** như `qwen3.5`: chúng có thể "nghĩ thành tiếng" trong một khối `<think>…</think>` trước khi trả lời. Với tác vụ có cấu trúc và đã được "mách nước" bằng few-shot này, phần suy luận chủ yếu làm **chậm** chứ ít cải thiện chất lượng, nên ta **tắt nó theo mặc định** (`TEXT2SPARQL_THINK=0`, gửi `think:false` cho Ollama). `gemma4:31b` vốn không phải mô hình suy luận nên không phát khối `<think>` — nhưng bộ parse vẫn cắt bỏ nó để công cụ dùng được với cả hai loại mô hình:

```python
_THINK = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)

def _parse(content: str) -> dict:
    content = _THINK.sub("", content).strip()   # bỏ phần suy luận
    ...
```

### Bước 4 — Thực thi và hiển thị kết quả

Câu SPARQL được chạy bằng `rdflib`. Khác với SQL, kết quả SPARQL có nhiều dạng, nên ta chuẩn hoá hết về dạng "cột + dòng":

- **SELECT** → các biến là cột, mỗi binding là một dòng.
- **ASK** → một giá trị boolean.
- **CONSTRUCT / DESCRIBE** → các bộ ba (subject, predicate, object).

```python
def run_query(source: str, sparql: str) -> QueryResult:
    if not settings.allow_update and _UPDATE_RE.search(sparql):
        raise ValueError("Updates are disabled; set TEXT2SPARQL_ALLOW_UPDATE=1 ...")
    result = GraphSource(source).query(sparql)
    if result.type == "ASK":
        return QueryResult(["ask"], [[bool(result.askAnswer)]], 1, False)
    if result.type in ("CONSTRUCT", "DESCRIBE"):
        ...   # trả về các bộ ba
    columns = [str(v) for v in result.vars]   # SELECT
    ...
```

Lưu ý về **an toàn**: SPARQL endpoint thường chỉ cho đọc, nên mặc định ta **từ chối** mọi câu lệnh Update (`INSERT`/`DELETE`/`LOAD`…). Muốn cho phép ghi, đặt `TEXT2SPARQL_ALLOW_UPDATE=1`.

### Bước 5 — Tự sửa lỗi (self-repair)

Mô hình nhỏ thỉnh thoảng viết sai cú pháp hoặc dùng nhầm tên thuộc tính. Thay vì bắt người dùng tự sửa, ta thêm một **vòng tự sửa**: nếu câu SPARQL **chạy báo lỗi**, ta đưa nguyên thông báo lỗi của engine ngược lại cho mô hình và yêu cầu sửa, tối đa `TEXT2SPARQL_MAX_ATTEMPTS` lần (mặc định 2).

```python
for attempt in range(1, settings.max_attempts + 1):
    data = llm.generate_sparql(SYSTEM_PROMPT, prompt)
    try:
        return graph.run_query(source, data["sparql"])   # chạy được → xong
    except Exception as e:
        prompt = base_prompt + _REPAIR.format(sparql=data["sparql"], problem=str(e))
```

Một lựa chọn thiết kế quan trọng: ta **chỉ** tự sửa khi *lỗi*, chứ không sửa khi truy vấn hợp lệ nhưng trả về **0 dòng**. Với mô hình nhỏ, việc ép sửa một câu "0 dòng" thường biến một truy vấn đúng thành sai — mà 0 dòng đôi khi lại chính là câu trả lời đúng. Lỗi cú pháp/tên thuộc tính thì ngược lại: gần như luôn sửa được nhờ chính thông báo lỗi cộng với dữ liệu mẫu.

## Chạy thử trên một đồ thị mẫu

Chúng ta tạo một đồ thị `shop_demo.ttl` mô phỏng một cửa hàng nhỏ, mô hình hoá bằng từ vựng **chuẩn schema.org** — `schema:Person`, `schema:Product`, `schema:Order`, `schema:OrderItem`, `schema:Invoice` — và **không có khối ontology mô tả nào** (lược đồ ngầm hiểu qua dữ liệu). Alice là người đặt nhiều đơn nhất (4 đơn).

```bash
text2sparql ingest examples/shop_demo.ttl
text2sparql run "Which customer placed the most orders?"
```

Công cụ đưa toàn bộ lược đồ (5 lớp) kèm dữ liệu mẫu cho mô hình. Đây là câu SPARQL mà **`gemma-4-31b-it` thực sự sinh ra** (ổn định qua các lần chạy):

```sparql
PREFIX ex: <http://example.org/shop#>
PREFIX schema: <https://schema.org/>
SELECT ?customerName WHERE {
  ?order a schema:Order ;
         schema:customer ?customer .
  ?customer schema:name ?customerName .
}
GROUP BY ?customerName
ORDER BY DESC(COUNT(?order))
LIMIT 1
```

Và kết quả thực thi:

```
 customerName
--------------
 Alice Nguyen
```

Đúng khách hàng cần tìm. Chú ý cách mô hình tự dùng `schema:customer` để "đi" từ đơn hàng sang khách hàng — nhờ thông tin `schema:customer -> schema:Person` mà bước nội suy ghi lại trong tài liệu lớp `schema:Order`, cộng với việc nó vốn "biết" từ vựng schema.org. (Điểm nhỏ duy nhất: gemma chỉ chiếu cột tên, không kèm cột đếm `4` — đủ để trả lời "*khách hàng nào*", nhưng vì thế bộ `eval` chấm strict vẫn tính trượt câu này; xem mục *Đo độ chính xác*.)

### Còn endpoint khổng lồ như DBpedia?

Vì `rdflib` nói chuyện được với endpoint từ xa, về nguyên tắc ta có thể trỏ thẳng vào một SPARQL endpoint — cùng một đối tượng `Graph`, cùng đường nội suy và thực thi, chỉ khác nguồn. Nhưng với một endpoint **khổng lồ** như DBpedia hay Wikidata thì đây là **một bài toán khác hẳn**, nằm ngoài phạm vi bài demo này: ontology hàng nghìn lớp không thể nhét trọn vào prompt, và việc nội suy bằng cách quét trực tiếp một đồ thị hàng triệu thực thể sẽ treo. Cách xử lý ở quy mô đó — chọn lọc lược đồ, nạp ontology theo namespace, liên kết thực thể — được trình bày riêng trong [Kế hoạch mở rộng](ke-hoach-mo-rong.md).

## Sức mạnh thật sự: truy vấn theo cấu trúc đồ thị

Đồ thị `shop_demo` ở trên thật ra chỉ là lược đồ quan hệ "dịch" sang RDF — chưa cho thấy vì sao lại cần đến đồ thị. Để thấy rõ điểm mạnh, ta dùng đồ thị thứ hai, `examples/acme_kg.ttl`, mô phỏng một công ty công nghệ với những thứ mà SQL rất khó diễn đạt:

- **Cây phân cấp lớp**: `Manager` ⊑ `Employee` ⊑ `Person` ⊑ `Agent` (ngầm hiểu qua kiểu được *vật chất hoá*).
- **Chuỗi quản lý bắc cầu**: `org:reportsTo` — nhân viên → trưởng nhóm → CTO → CEO.
- **Lồng nhau về địa lý**: `gn:locatedIn` — toà nhà → thành phố → quốc gia.
- **Lồng nhau về tổ chức**: `org:subOrganizationOf` — team → phòng ban → công ty.
- **Cây kỹ năng**: `skos:broader` — Python → Lập trình; NLP → Học máy.

Bí quyết để trả lời những câu hỏi này là **property path** của SPARQL — toán tử `+` (một-hoặc-nhiều bước), `*` (không-hoặc-nhiều bước) và `/` (nối chuỗi). Đây chính là thứ làm nên khác biệt với SQL, và ta đã "mách nước" cho mô hình trong system prompt.

```bash
text2sparql ingest examples/acme_kg.ttl
```

**1. Truy vấn theo lớp trong cây phân cấp.** Cây lớp `Manager ⊑ Employee ⊑ Person ⊑ Agent` ở đây **không** được khai báo tường minh bằng `rdfs:subClassOf` — đồ thị mẫu là dữ liệu thuần. Thay vào đó ta **vật chất hoá kiểu (materialize)**: mỗi cá nhân được gán sẵn *cả chuỗi lớp cha* (`ex:sofia a org:Manager, org:Employee, org:Person, org:Agent`). Nhờ vậy câu hỏi *"liệt kê tất cả nhân viên"* chỉ cần truy vấn đơn giản nhất mà vẫn gom được cả các quản lý, không cần mô hình nhớ tới `rdfs:subClassOf*`:

```sparql
SELECT ?name WHERE { ?p a org:Employee ; schema:name ?name }
```

> Trả về cả 7 người — kể cả CEO/CTO (được gán lớp `Manager`) — vì kiểu đã được vật chất hoá. Cách này chuyển gánh nặng "suy luận phân cấp" từ *lúc truy vấn* sang *lúc nạp dữ liệu*: ổn định hơn hẳn với mọi cỡ mô hình. (Nếu đồ thị của bạn *có* khai báo `rdfs:subClassOf`, công cụ vẫn đọc được cây lớp đó ở Bước 1, và mô hình có thể suy luận lúc truy vấn bằng property path `?p a/rdfs:subClassOf* org:Employee`.)

**2. Bắc cầu trên quan hệ.** *"Tom báo cáo cho những ai, trực tiếp lẫn gián tiếp?"* — quan hệ `org:reportsTo` chỉ lưu **một bước**, nên cần property path `+` để leo hết chuỗi:

```sparql
SELECT ?boss WHERE {
  ?tom schema:name "Tom Becker" ; org:reportsTo+ ?b .
  ?b schema:name ?boss .
}
#  → Mei Lin → Raj Patel → Sofia Reyes
```

**3. Nối chuỗi nhiều quan hệ.** *"Trụ sở ACME nằm ở quốc gia nào?"* — đi từ công ty qua `basedIn` rồi bắc cầu `locatedIn` cho tới khi gặp một `Country`:

```sparql
SELECT ?country WHERE {
  ?acme schema:name "ACME Corp" ; org:basedIn/gn:locatedIn+ ?place .
  ?place a gn:Country ; schema:name ?country .
}
#  → United States  (ACME → ACME HQ → San Francisco → United States)
```

**4. Đi theo cây kỹ năng.** *"Ai có kỹ năng thuộc nhóm học máy?"* — `skos:broader*` gom cả NLP, Computer Vision… về nhánh `ex:ml`:

```sparql
SELECT DISTINCT ?name WHERE {
  ?ml schema:name "Machine Learning" .
  ?p org:hasSkill/skos:broader* ?ml ; schema:name ?name .
}
#  → Sofia, Raj (ML) + Omar, Lina (NLP, là con của ML)
```

Cả bốn câu trên, nếu làm bằng SQL, đều cần đến truy vấn đệ quy (`WITH RECURSIVE`) dài dòng. Với SPARQL trên đồ thị, mỗi câu chỉ gọn trong một dòng property path — và đó chính là lý do ta chọn mô hình hoá dữ liệu dưới dạng đồ thị.

## Đo độ chính xác (evaluation)

Với một công cụ dựa trên LLM, "có vẻ chạy đúng" là chưa đủ — mỗi lần đổi prompt, đổi dữ liệu hay đổi mô hình đều có thể *âm thầm* làm hỏng một câu đang đúng. Vì vậy ta đính kèm một bộ chấm điểm nhỏ: tệp [`examples/eval.jsonl`](../examples/eval.jsonl) liệt kê các câu hỏi vàng kèm **tập đáp án mong đợi**.

```jsonl
{"graph": "examples/acme_kg.ttl", "question": "List everyone who is an employee, including managers", "expect": ["Sofia Reyes", "Raj Patel", "Mei Lin", "Omar Haddad", "Tom Becker", "Ana Costa", "Lina Park"]}
{"graph": "examples/acme_kg.ttl", "question": "Who does Tom Becker report to, directly or indirectly?", "expect": ["Mei Lin", "Raj Patel", "Sofia Reyes"]}
```

Lệnh `eval` nạp từng đồ thị, chạy trọn vòng (sinh SPARQL → thực thi → tự sửa nếu lỗi), rồi so kết quả với `expect` và in bảng PASS/FAIL kèm điểm số:

```bash
text2sparql eval
```

Cách so khớp được viết "khoan dung" với hình thức trình bày: ta gom mọi giá trị ô trong kết quả thành một tập và so với `expect`, nên thứ tự dòng hay tên cột không ảnh hưởng — chỉ **nội dung câu trả lời** mới quyết định đúng/sai. Nhờ đó, mỗi khi tinh chỉnh prompt hay nâng cấp mô hình, bạn biết ngay mình **tiến hay lùi**.

Chính bộ `eval` này cho thấy **lựa chọn mô hình quan trọng đến mức nào**. Trên 8 câu hỏi vàng (chi tiết trong [báo cáo eval gemma](eval-gemma-4-31b-it.md)):

| Mô hình | Điểm | Ghi chú |
|---|---|---|
| **gemma4:31b** (instruct ~30B) | **≈7/8** | đúng mọi dạng câu *đồ thị* khó: phân cấp lớp, bắc cầu, nối chuỗi, cây kỹ năng |
| qwen3.5:4b (nội bộ, Ollama) | 2/8 | trả về IRI thay vì tên, sai gộp nhóm/lọc, và cả lỗi cú pháp SPARQL |

Kết luận thực dụng: mô hình 4B quá nhỏ cho property path và việc "join" giữa các lớp; còn một mô hình instruct tầm ~30B như **gemma4:31b** đã đúng **mọi dạng câu đồ thị khó** — đủ tốt cho một công cụ nội bộ.

> **Lưu ý cách chạy.** Công cụ này chạy mô hình **local qua Ollama** (`ollama pull gemma4:31b`). Riêng các con số eval ở trên được đo bằng cách chạy `gemma4:31b` trên một máy đủ mạnh — máy dev của chúng tôi không kham nổi một mô hình ~30B. Vì prompt và phần grounding là *model-agnostic*, điểm số vẫn phản ánh đúng năng lực mô hình bất kể chạy ở đâu.

## Lưu ý khi vận hành

- **Nội suy là phép gần đúng.** Ta suy cấu trúc từ dữ liệu mẫu, nên với đồ thị rất lớn hoặc thưa, vài thuộc tính hiếm có thể bị bỏ sót. Tăng `SAMPLE_LIMIT` nếu cần đầy đủ hơn.
- **Chế độ ghi.** Mặc định mọi câu lệnh Update bị chặn. Chỉ bật `TEXT2SPARQL_ALLOW_UPDATE=1` khi bạn thực sự muốn ghi vào một store của mình.
- **Mô hình không phải lúc nào cũng đúng.** LLM có thể quên `PREFIX`, dùng sai chiều của object property, hoặc hiểu nhầm câu hỏi. Đó là lý do công cụ luôn **in ra câu SPARQL** (cả `run` lẫn `ask`) để bạn kiểm tra trước khi tin kết quả — và vì sao ta cần bộ `eval` để đo độ chính xác một cách khách quan.

## Kết luận

Chúng ta vừa xây một công cụ Text-to-SPARQL hoàn chỉnh, chạy **hoàn toàn nội bộ**: từ việc suy ra ontology của một đồ thị RDF, cho tới sinh và thực thi SPARQL bằng một LLM mã nguồn mở. Điểm cốt lõi cần nhớ là với RDF, cấu trúc không cho sẵn dưới dạng lược đồ mà phải **suy ra từ chính dữ liệu**; và với đồ thị cỡ vừa, công thức thắng cuộc đơn giản đến bất ngờ — **đưa cả lược đồ + vài bộ ba thật vào prompt**, không cần embedding hay kho vector.

Bài này cố tình giữ **gọn trong phạm vi một demo**: một đồ thị nhỏ/vừa, cả ontology đưa trọn vào prompt, không embedding, không kho vector. Đó là lý do công thức thắng cuộc đơn giản đến bất ngờ. Từ nền tảng này, hướng mở rộng đáng giá nhất là đưa công cụ lên **đồ thị/endpoint rất lớn** (DBpedia, Wikidata), nơi ontology không còn nhét trọn vào prompt:

- **Chọn lọc lược đồ (schema selection).** Thay vì đưa cả ontology, chỉ **truy hồi phần lược đồ liên quan** tới câu hỏi — khớp từ khoá + lan theo cạnh `rdfs:domain`/`rdfs:range`, embedding là phương án dự phòng.
- **Nạp ontology theo namespace.** Dữ liệu thuần (như hai đồ thị mẫu ở đây) không kèm định nghĩa lớp/thuộc tính; có thể **nạp ontology đã công bố tại chính namespace** của chúng (schema.org, W3C Org, SKOS, `dbo:`…) để làm giàu ngữ nghĩa cho bước chọn lọc.
- **Liên kết thực thể (entity linking).** Ánh xạ tên riêng trong câu hỏi ("Berlin") sang IRI thật (`dbr:Berlin`) trước khi sinh truy vấn — mấu chốt để chạy đúng trên KG thật.
- **Mô hình mạnh hơn khi cần chính xác tuyệt đối.** Bộ `eval` cho phép đo lại tác động ngay; ví dụ MiniMax M3 (từ xa) đạt 8/8 trên bộ câu hỏi này. Ngược lại, phần lớn mô hình *tinh chỉnh riêng cho SPARQL* lại gắn chặt vào **một** KG cụ thể, nên với đồ thị tự định nghĩa, một mô hình **chỉ-dẫn tổng quát** như `gemma4:31b` cộng grounding tại chỗ thường là lựa chọn đúng hơn.

Chi tiết kiến trúc và lộ trình cho các hướng trên nằm trong [Kế hoạch mở rộng](ke-hoach-mo-rong.md).

Hy vọng bài viết giúp các bạn tự chủ công nghệ Text-to-SPARQL ngay trên hạ tầng của mình. Chúc các bạn thực hành vui!
