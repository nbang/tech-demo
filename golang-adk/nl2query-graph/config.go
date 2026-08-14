// Copyright 2026.
//
// config.go loads runtime configuration from a .env file (if present) plus the
// process environment, so you can edit .env directly like the other demos.

package main

import (
	"fmt"
	"os"

	"github.com/joho/godotenv"
)

// Config holds everything the demo needs, sourced from .env / environment.
type Config struct {
	// LLM (OpenAI-compatible endpoint).
	APIKey  string
	BaseURL string
	Model   string

	// Query targets.
	SQLitePath string // path to the SQLite .db file (SQL branch)
	TTLPath    string // path to the Turtle .ttl file (SPARQL branch)
}

// LoadConfig reads .env (best-effort) then the environment, applying defaults.
func LoadConfig() (*Config, error) {
	// Best-effort: a missing .env is fine, real env vars still win.
	_ = godotenv.Load()

	c := &Config{
		APIKey:     envOr("OPENAI_API_KEY", os.Getenv("NVIDIA_API_KEY")),
		BaseURL:    envOr("OPENAI_BASE_URL", "https://integrate.api.nvidia.com/v1"),
		Model:      envOr("OPENAI_MODEL", "nvidia/gemma4:31b"),
		SQLitePath: envOr("SQLITE_PATH", "./examples/shop.db"),
		TTLPath:    envOr("TTL_PATH", "./examples/kg.ttl"),
	}
	if c.APIKey == "" {
		return nil, fmt.Errorf("OPENAI_API_KEY (or NVIDIA_API_KEY) is required — set it in .env")
	}
	return c, nil
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
