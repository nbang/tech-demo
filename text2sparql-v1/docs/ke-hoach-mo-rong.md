# Kế hoạch mở rộng text2sparql — từ demo tới đồ thị lớn (DBpedia/Wikidata)

> Tài liệu này là **lộ trình kỹ thuật**, không phải phần của bài demo. Bài demo
> ([huong-dan-text2sparql.md](huong-dan-text2sparql.md)) cố tình giữ đơn giản: đồ thị nhỏ/vừa,
> cả ontology đưa trọn vào prompt, không embedding, không kho vector. Tài liệu này mô tả cách
> đưa công cụ lên các endpoint **khổng lồ** mà vẫn giữ hai ràng buộc gốc: **self-hosted** và
> **mô hình cố định `gemma4:31b`** (mọi cải thiện độ chính xác đến từ retrieval/grounding tốt hơn,
> không phải đổi mô hình).

## 1. Mục tiêu & nguyên tắc

**Mục tiêu.** `text2sparql ingest "https://dbpedia.org/sparql"` chạy trong vài giây (thay vì treo),
và `run` trả lời đúng các câu hỏi thật trên DBpedia.

**Nguyên tắc thiết kế:**

1. **Không phá đường đi hiện tại.** Đồ thị nhỏ/vừa vẫn dùng đúng luồng cũ (introspect ABox +
   cả ontology vào prompt). Đường đi cho đồ thị lớn là **opt-in**, kích hoạt theo nguồn.
2. **Đo, đừng đoán.** Mọi thay đổi được chấm bằng `eval` trên một bộ câu hỏi vàng của DBpedia
   (QALD-9 / LC-QuAD 2.0). Không có số → không merge.
3. **Giữ self-hosted.** Embedding chạy local (ví dụ `nomic-embed-text` qua Ollama); entity linking
   ưu tiên full-text index của chính endpoint. Mọi lệnh gọi ra ngoài đều là **opt-in**.
4. **Mô hình bất biến.** `gemma4:31b`. Vì context có hạn, **độ chính xác của bước chọn lọc lược đồ
   là yếu tố quyết định** — phải đưa cho mô hình một lát cắt *nhỏ và đúng*.

## 2. Vì sao demo hiện tại không lên nổi DBpedia

Bốn "bức tường", đều nằm ở chỗ *cả ontology* được nội suy trực tiếp rồi nhồi vào prompt:

| # | Bức tường | Vị trí | Vì sao vỡ trên DBpedia |
|---|---|---|---|
| 1 | Đếm/quét ABox trực tiếp | [graph.py:156](../text2sparql/graph.py#L156), [graph.py:169](../text2sparql/graph.py#L169) | `COUNT(DISTINCT ?s)` trên `owl:Thing`/`dbo:Person` mất ~15s **mỗi lớp** × 200 lớp → treo + rate-limit |
| 2 | Cả ontology vào prompt | [engine.py:125](../text2sparql/engine.py#L125) | `dbo:` có ~800 lớp / ~3.000 thuộc tính — không vừa context, và precision sụp |
| 3 | Lát cắt lớp tuỳ tiện | [graph.py:140](../text2sparql/graph.py#L140) `LIMIT max_classes` | `LIMIT` không sắp xếp → thường **không chứa** lớp câu hỏi cần (`dbo:Country`) |
| 4 | Không có entity linking | — | "Berlin ở nước nào?" cần `dbr:Berlin`; grounding hiện lấy thực thể **tuỳ tiện** |

## 3. Kiến trúc mục tiêu: *retrieve-then-generate*

Đổi từ "gửi tất cả" sang "chọn lọc rồi sinh". `ingest` **dựng index một lần**; `_build_prompt`
**chọn lát cắt nhỏ theo từng câu hỏi**.

```
                          ┌──────────── ingest (một lần) ────────────┐
  namespace ontologies ──▶│ nạp TBox theo namespace  ─┐              │
  (schema.org, dbo:, …)   │                           ▼              │
  endpoint / RDF file ───▶│ introspect (ABox, nếu rẻ) → INDEX lược đồ │  (BM25 + embedding local)
                          └──────────────────────────────────────────┘
                                                     │
  câu hỏi ─┬─▶ schema selection (top-K lớp/thuộc tính liên quan) ─┐
           └─▶ entity linking (Berlin → dbr:Berlin) ──────────────┤
                                                                   ▼
                              prompt = lát cắt lược đồ + IRI thật + câu hỏi
                                                                   ▼
                                    gemma4:31b ─▶ SPARQL ─▶ thực thi ─▶ kết quả
```

## 4. Các hạng mục (theo pha)

### Pha 1 — Nạp ontology theo namespace (`vocab.py`)  ·  *rủi ro thấp, giá trị cao*

**Vấn đề.** Dữ liệu thuần (shop/acme, và phần lớn KG thật) **không chứa TBox**: chúng *dùng*
`schema:`, `org:`, `gn:`, `skos:` nhưng không *định nghĩa* chúng. Bước introspect hiện chỉ suy
"hình dạng" từ dữ liệu, thiếu `rdfs:domain/range`, `subClassOf`, label, comment.

**Cách làm.** Với mỗi namespace xuất hiện trong đồ thị, nạp ontology đã công bố tại đó và **làm giàu**
tài liệu lớp/thuộc tính:

```python
# vocab.py
VOCAB_DOCS = {
    "https://schema.org/":                  "https://schema.org/version/latest/schemaorg-current-https.ttl",
    "http://www.w3.org/ns/org#":            "http://www.w3.org/ns/org",       # content-negotiation → RDF
    "http://www.w3.org/2004/02/skos/core#": "http://www.w3.org/2004/02/skos/core",
    "http://www.geonames.org/ontology#":    "http://www.geonames.org/ontology/ontology_v3.3.rdf",
    "http://dbpedia.org/ontology/":         "https://databus.dbpedia.org/.../ontology.ttl",
}

def load_vocab(namespace_iri) -> Graph:
    # 1) registry hit → tải doc;  2) else thử deref chính namespace IRI;  3) fail → bỏ qua (vd ex:)
    # Cache vào settings.data_dir → chỉ tải mạng một lần, sau đó chạy offline.
```

**Bẫy cần tránh.** schema.org có ~3.000 term — nạp cả thì tái tạo đúng vấn đề "phình prompt".
→ **Chỉ giữ term mà ABox thực sự dùng** (giao TBox với danh sách predicate/class introspect được),
cộng hàng xóm domain/range.

**Tệp:** `vocab.py` (mới); `engine.ingest` ([engine.py:66](../text2sparql/engine.py#L66)) gọi làm giàu;
`ClassInfo`/`Property` ([graph.py:71](../text2sparql/graph.py#L71)) thêm trường definition.
**Đầu ra:** tài liệu lớp giàu hơn → chạy được ngay trên acme/shop (so sánh before/after
`org:reportsTo`, `gn:locatedIn`). **Rủi ro:** phụ thuộc mạng → giải quyết bằng cache + bỏ qua khi fail.

### Pha 2 — Chọn lọc lược đồ / RAG (`retrieval.py`)  ·  *trọng tâm*

**Vấn đề.** Bức tường #2 và #3. **Cách làm** (theo thứ tự tăng dần chi phí):

```python
def select_schema(question, index, k=15):
    seeds = bm25(index, question, k)                 # 1) lexical: rẻ, mạnh vì label KG mô tả tốt
    if weak(seeds):
        seeds += vector_topk(index, embed(question)) # 2) embedding local (nomic-embed-text) cho paraphrase
    return expand_along_domain_range(seeds, index)   # 3) lan theo domain/range để kéo lớp "join" vào
```

Đổi [engine.py:125](../text2sparql/engine.py#L125) từ `"\n\n".join(documents)` thành
`"\n\n".join(select_schema(question, index))`. Repair loop và JSON contract giữ nguyên.

**Tệp:** `retrieval.py` (mới); `ingest` dựng index; `_build_prompt` gọi selection.
**Đầu ra:** prompt nhỏ, đúng lớp cần. **Rủi ro:** miss lớp đúng → giảm nhẹ bằng graph-expansion + đo bằng `eval`.

### Pha 3 — Ingest theo TBox cho endpoint lớn (`introspect_tbox`)  ·  *gỡ bức tường #1*

**Vấn đề.** Không thể quét ABox của DBpedia. **Cách làm.** Với endpoint lớn, đọc lớp/thuộc tính/
domain/range **từ file ontology** (dbo, vài MB, nạp một lần) — **không đụng ABox**. Bỏ `COUNT`,
hoặc lấy số liệu từ **VoID** nếu có.

```python
def introspect_tbox(ontology_source):    # dbo .ttl parse local
    # ?c a owl:Class ; mỗi property: rdfs:domain/range → ClassInfo.properties ; label/comment sẵn có
```

**Tệp:** `graph.py` (thêm nhánh); `ingest --ontology dbo.ttl`.
**Đầu ra:** `ingest dbpedia` xong trong vài giây. **Rủi ro:** TBox ≠ dữ liệu thật → bù bằng grounding (Pha 4).

### Pha 4 — Liên kết thực thể (`linking.py`)  ·  *đúng/sai câu trả lời nằm ở đây*

**Vấn đề.** Chọn đúng lớp/thuộc tính vẫn chưa đủ: mô hình không biết "Berlin" = `dbr:Berlin`.
**Cách làm:**

- **Rẻ, self-hosted:** full-text của Virtuoso — `?s rdfs:label ?l . ?l bif:contains "Berlin" . ?s a dbo:Place`
  (bounded, có index).
- **Hoặc** DBpedia Lookup API — nhưng ra ngoài máy → **opt-in**.

Đưa IRI tìm được vào đúng khối example-triples hiện có → mô hình thấy `dbr:Berlin a dbo:City ; dbo:country dbr:Germany .`

**Tệp:** `linking.py` (mới); `_build_prompt` chèn IRI đã link vào grounding.
**Đầu ra:** tăng mạnh accuracy trên KG thật. **Rủi ro:** nhập nhằng tên → lấy top-N ứng viên, để mô hình chọn theo ngữ cảnh.

### Pha 5 — Vững vàng khi chạy endpoint thật

- **Timeout + subquery có `LIMIT`** cho mọi truy vấn nội suy; retry/backoff trên 429/504 trong
  [graph.py `query()`](../text2sparql/graph.py#L57) (soi mẫu sẵn có ở [llm.py:80](../text2sparql/llm.py#L80)).
- **Phân trang** `LIMIT/OFFSET` (Virtuoso mặc định cắt ~10.000 dòng); nêu rõ cap là của endpoint,
  không phải của tool ([run_query](../text2sparql/graph.py#L309)).
- **Seed prefix phổ biến** (`dbo:`, `dbr:`, `dbp:`, `dct:`, `geo:`) trong
  [GraphSource.__init__](../text2sparql/graph.py#L54) để CURIE sinh ra tự nhiên.

### Pha 6 — Mở rộng `eval`

Thêm bộ vàng DBpedia từ **QALD-9** / **LC-QuAD 2.0** vào [eval](../text2sparql/eval.py). Đây là cách
biến "schema selection có giúp không?" thành **con số** — và để tinh chỉnh K, tỉ lệ lexical/embedding,
và bộ linker mà **không đổi mô hình**.

## 5. Bố cục module đề xuất

```
text2sparql/
  graph.py      # + introspect_tbox(); count có timeout; probe full-text cho entity
  vocab.py      # MỚI: nạp + cache ontology theo namespace, làm giàu class/property docs
  retrieval.py  # MỚI: build_index(docs); select_schema(question) = BM25 → embed → graph-expand
  linking.py    # MỚI: link_entities(question) → IRIs (full-text / Lookup)
  engine.py     # ingest dựng index; _build_prompt gọi select_schema + link_entities
  llm.py        # không đổi (gemma4:31b)
```

## 6. Thứ tự triển khai đề xuất

1. **Pha 1 (`vocab.py`)** — chạy được ngay trên acme/shop, làm nền cho RAG.
2. **Pha 2 (`retrieval.py`)** — khiến prompt vừa context; đây là thay đổi cốt lõi.
3. **Pha 6 (eval DBpedia)** — có thước đo trước khi đụng endpoint lớn.
4. **Pha 3 (`introspect_tbox`)** — `ingest dbpedia` hết treo.
5. **Pha 4 (`linking.py`)** — làm cho câu trả lời *đúng*.
6. **Pha 5 (hardening)** — làm đường chạy production ổn định.

> Đòn bẩy lớn nhất cho *chạy được*: **Pha 1 + 2 + 3**. Đòn bẩy lớn nhất cho *trả lời đúng*: **Pha 4**.
