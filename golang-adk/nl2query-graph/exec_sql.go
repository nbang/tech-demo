// Copyright 2026.
//
// exec_sql.go runs generated SQL against a SQLite database file (pure-Go
// driver, no cgo). On first run it seeds a small sample schema so you can
// validate the demo immediately.

package main

import (
	"context"
	"database/sql"
	"fmt"
	"strings"

	_ "modernc.org/sqlite" // registers the "sqlite" driver
)

// SQLStore is a thin wrapper around a SQLite connection.
type SQLStore struct {
	db *sql.DB
}

// OpenSQLStore opens (creating if needed) the SQLite file and ensures the
// sample schema + rows exist.
func OpenSQLStore(path string) (*SQLStore, error) {
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, fmt.Errorf("open sqlite %q: %w", path, err)
	}
	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("ping sqlite %q: %w", path, err)
	}
	s := &SQLStore{db: db}
	if err := s.seed(); err != nil {
		return nil, err
	}
	return s, nil
}

// seed creates the sample tables and inserts rows if the products table is empty.
func (s *SQLStore) seed() error {
	const ddl = `
CREATE TABLE IF NOT EXISTS products (
	id       INTEGER PRIMARY KEY,
	name     TEXT    NOT NULL,
	price    REAL    NOT NULL,
	category TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS customers (
	id   INTEGER PRIMARY KEY,
	name TEXT    NOT NULL,
	city TEXT    NOT NULL
);`
	if _, err := s.db.Exec(ddl); err != nil {
		return fmt.Errorf("create schema: %w", err)
	}

	var n int
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM products`).Scan(&n); err != nil {
		return fmt.Errorf("count products: %w", err)
	}
	if n > 0 {
		return nil
	}

	const seed = `
INSERT INTO products (name, price, category) VALUES
	('Mechanical Keyboard', 129.00, 'peripherals'),
	('Wireless Mouse',       49.90, 'peripherals'),
	('4K Monitor',          349.00, 'displays'),
	('USB-C Hub',            79.50, 'accessories'),
	('Laptop Stand',        119.00, 'accessories'),
	('Noise-Cancel Headset',199.00, 'audio');
INSERT INTO customers (name, city) VALUES
	('Alice', 'Hanoi'),
	('Bob',   'Da Nang'),
	('Carol', 'Ho Chi Minh City');`
	if _, err := s.db.Exec(seed); err != nil {
		return fmt.Errorf("seed rows: %w", err)
	}
	return nil
}

// Query runs a SELECT and returns a formatted, human-readable table.
func (s *SQLStore) Query(ctx context.Context, query string) (string, error) {
	rows, err := s.db.QueryContext(ctx, query)
	if err != nil {
		return "", fmt.Errorf("execute: %w", err)
	}
	defer rows.Close()

	cols, err := rows.Columns()
	if err != nil {
		return "", err
	}

	var out strings.Builder
	out.WriteString(strings.Join(cols, " | "))
	out.WriteString("\n")

	count := 0
	for rows.Next() {
		vals := make([]any, len(cols))
		ptrs := make([]any, len(cols))
		for i := range vals {
			ptrs[i] = &vals[i]
		}
		if err := rows.Scan(ptrs...); err != nil {
			return "", err
		}
		cells := make([]string, len(cols))
		for i, v := range vals {
			cells[i] = fmt.Sprintf("%v", v)
		}
		out.WriteString(strings.Join(cells, " | "))
		out.WriteString("\n")
		count++
	}
	if err := rows.Err(); err != nil {
		return "", err
	}
	out.WriteString(fmt.Sprintf("(%d row(s))", count))
	return out.String(), nil
}

// Close releases the database handle.
func (s *SQLStore) Close() error { return s.db.Close() }
