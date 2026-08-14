package main

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// TestSeedRealShopDB materializes the real examples/shop.db (path from
// SQLITE_PATH, default ./examples/shop.db). Skipped unless SEED_REAL_DB=1 so
// the normal test run stays hermetic. Run with:
//
//	SEED_REAL_DB=1 go test -run TestSeedRealShopDB -v
func TestSeedRealShopDB(t *testing.T) {
	if os.Getenv("SEED_REAL_DB") == "" {
		t.Skip("set SEED_REAL_DB=1 to seed the real database")
	}
	path := os.Getenv("SQLITE_PATH")
	if path == "" {
		path = "./examples/shop.db"
	}
	s, err := OpenSQLStore(path)
	if err != nil {
		t.Fatalf("seed %q: %v", path, err)
	}
	defer s.Close()
	out, err := s.Query(context.Background(), "SELECT COUNT(*) AS products FROM products")
	if err != nil {
		t.Fatalf("verify: %v", err)
	}
	t.Logf("seeded %s\n%s", path, out)
}

func TestSQLStoreSeedAndQuery(t *testing.T) {
	path := filepath.Join(t.TempDir(), "shop.db")
	s, err := OpenSQLStore(path)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	defer s.Close()

	out, err := s.Query(context.Background(),
		"SELECT name, price FROM products WHERE price > 100 ORDER BY price")
	if err != nil {
		t.Fatalf("query: %v", err)
	}
	t.Logf("SQL result:\n%s", out)
	// keyboard 129, stand 119, headset 199, monitor 349 => 4 rows
	if !strings.Contains(out, "(4 row(s))") {
		t.Errorf("expected 4 rows, got:\n%s", out)
	}
	for _, want := range []string{"Mechanical Keyboard", "4K Monitor", "Laptop Stand", "Noise-Cancel Headset"} {
		if !strings.Contains(out, want) {
			t.Errorf("missing %q in:\n%s", want, out)
		}
	}
	if strings.Contains(out, "Wireless Mouse") {
		t.Errorf("Wireless Mouse (50) should be filtered out:\n%s", out)
	}
}

func TestTripleStoreProductsFilter(t *testing.T) {
	s, err := OpenTripleStore("examples/kg.ttl")
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	out, err := s.Query(`PREFIX ex: <http://example.org/>
SELECT ?name ?price WHERE {
  ?p a ex:Product .
  ?p ex:name ?name .
  ?p ex:price ?price .
  FILTER(?price > 100)
}`)
	if err != nil {
		t.Fatalf("query: %v", err)
	}
	t.Logf("SPARQL result:\n%s", out)
	if !strings.Contains(out, "(4 row(s))") {
		t.Errorf("expected 4 rows, got:\n%s", out)
	}
	if !strings.Contains(out, "Mechanical Keyboard") || !strings.Contains(out, "4K Monitor") {
		t.Errorf("expected keyboard+monitor in:\n%s", out)
	}
	if strings.Contains(out, "Wireless Mouse") {
		t.Errorf("Wireless Mouse (50) should be filtered out:\n%s", out)
	}
}

// TestSymmetricCategory checks that the SQL and SPARQL branches answer the same
// "products in the accessories category" question identically.
func TestSymmetricCategory(t *testing.T) {
	sq, err := OpenSQLStore(filepath.Join(t.TempDir(), "shop.db"))
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	defer sq.Close()
	sqlOut, err := sq.Query(context.Background(),
		"SELECT name FROM products WHERE category = 'accessories' ORDER BY name")
	if err != nil {
		t.Fatalf("sql query: %v", err)
	}

	ts, err := OpenTripleStore("examples/kg.ttl")
	if err != nil {
		t.Fatalf("open ttl: %v", err)
	}
	sparqlOut, err := ts.Query(`PREFIX ex: <http://example.org/>
SELECT ?name WHERE {
  ?p a ex:Product .
  ?p ex:category "accessories" .
  ?p ex:name ?name .
}`)
	if err != nil {
		t.Fatalf("sparql query: %v", err)
	}

	t.Logf("SQL:\n%s\n\nSPARQL:\n%s", sqlOut, sparqlOut)
	for _, want := range []string{"USB-C Hub", "Laptop Stand"} {
		if !strings.Contains(sqlOut, want) {
			t.Errorf("SQL missing %q", want)
		}
		if !strings.Contains(sparqlOut, want) {
			t.Errorf("SPARQL missing %q", want)
		}
	}
	if !strings.Contains(sqlOut, "(2 row(s))") || !strings.Contains(sparqlOut, "(2 row(s))") {
		t.Errorf("expected 2 rows from both branches")
	}
}

// TestBuildHybridGraph validates the fan-out/parallel/join/synthesis wiring:
// workflowagent.New rejects malformed edges, so a successful build proves the
// graph is structurally sound — no live endpoint needed.
func TestBuildHybridGraph(t *testing.T) {
	llm := NewOpenAIModel("dummy-model", "http://localhost:0", "dummy-key")
	sq, err := OpenSQLStore(filepath.Join(t.TempDir(), "shop.db"))
	if err != nil {
		t.Fatalf("sqlite: %v", err)
	}
	defer sq.Close()
	ts, err := OpenTripleStore("examples/kg.ttl")
	if err != nil {
		t.Fatalf("ttl: %v", err)
	}
	a, err := buildHybrid(llm, sq, ts)
	if err != nil {
		t.Fatalf("buildHybrid: %v", err)
	}
	if a == nil {
		t.Fatal("buildHybrid returned nil agent")
	}
}

func TestTripleStoreSocialJoin(t *testing.T) {
	s, err := OpenTripleStore("examples/kg.ttl")
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	out, err := s.Query(`PREFIX ex: <http://example.org/>
SELECT ?name WHERE {
  ex:alice ex:knows ?f .
  ?f ex:name ?name .
}`)
	if err != nil {
		t.Fatalf("query: %v", err)
	}
	t.Logf("SPARQL join result:\n%s", out)
	if !strings.Contains(out, "Bob") || !strings.Contains(out, "Carol") {
		t.Errorf("expected Alice to know Bob and Carol, got:\n%s", out)
	}
	if !strings.Contains(out, "(2 row(s))") {
		t.Errorf("expected 2 rows, got:\n%s", out)
	}
}
