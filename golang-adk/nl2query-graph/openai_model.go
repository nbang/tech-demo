// Copyright 2026.
//
// openai_model.go is a minimal adk-go model.LLM adapter that talks to any
// OpenAI-compatible /chat/completions endpoint (NVIDIA integrate.api.nvidia.com,
// vLLM, Ollama's OpenAI shim, etc.) using the official OpenAI Go client
// (github.com/openai/openai-go).
//
// ADK-Go v2.0 ships only the `gemini` and `apigee` model packages, so this is
// the supported way to use a different provider: implement the small model.LLM
// interface and hand it to llmagent. The heavy lifting (HTTP, retries, JSON) is
// delegated to the OpenAI SDK; this file only maps between ADK's genai types
// and the SDK's chat types.
//
// It is deliberately non-streaming and text-only — enough for the classifier
// node in this demo. It ignores tool calls and multi-modal parts.

package main

import (
	"context"
	"fmt"
	"iter"
	"strings"

	"github.com/openai/openai-go/v3"
	"github.com/openai/openai-go/v3/option"
	"github.com/openai/openai-go/v3/shared"

	"google.golang.org/adk/v2/model"
	"google.golang.org/genai"
)

// partsText concatenates the text parts of a genai.Content.
func partsText(parts []*genai.Part) string {
	var s string
	for _, p := range parts {
		if p != nil {
			s += p.Text
		}
	}
	return s
}

// OpenAIModel implements model.LLM against an OpenAI-compatible chat endpoint.
type OpenAIModel struct {
	modelName string
	client    openai.Client
}

// NewOpenAIModel builds a model. baseURL is the API root (with the trailing
// /v1 but without /chat/completions), e.g. "https://integrate.api.nvidia.com/v1".
func NewOpenAIModel(modelName, baseURL, apiKey string) *OpenAIModel {
	return &OpenAIModel{
		modelName: modelName,
		client: openai.NewClient(
			option.WithBaseURL(baseURL),
			option.WithAPIKey(apiKey),
		),
	}
}

// Name reports the model id, satisfying model.LLM.
func (m *OpenAIModel) Name() string { return m.modelName }

// Complete is a convenience one-shot: send a system + user prompt and return
// the model's text reply. Used by the query-generation nodes.
func (m *OpenAIModel) Complete(ctx context.Context, system, user string) (string, error) {
	req := &model.LLMRequest{
		Model:    m.modelName,
		Contents: []*genai.Content{{Role: "user", Parts: []*genai.Part{{Text: user}}}},
		Config:   &genai.GenerateContentConfig{SystemInstruction: &genai.Content{Parts: []*genai.Part{{Text: system}}}},
	}
	var sb strings.Builder
	for resp, err := range m.GenerateContent(ctx, req, false) {
		if err != nil {
			return "", err
		}
		if resp.Content != nil {
			sb.WriteString(partsText(resp.Content.Parts))
		}
	}
	return strings.TrimSpace(sb.String()), nil
}

// GenerateContent performs a single blocking chat completion and yields one
// LLMResponse. The `stream` flag is accepted but always served as one final
// (non-partial) response, which is sufficient for a single-shot classifier.
func (m *OpenAIModel) GenerateContent(ctx context.Context, req *model.LLMRequest, stream bool) iter.Seq2[*model.LLMResponse, error] {
	return func(yield func(*model.LLMResponse, error) bool) {
		msgs := make([]openai.ChatCompletionMessageParamUnion, 0, len(req.Contents)+1)
		if req.Config != nil && req.Config.SystemInstruction != nil {
			if s := partsText(req.Config.SystemInstruction.Parts); s != "" {
				msgs = append(msgs, openai.SystemMessage(s))
			}
		}
		for _, c := range req.Contents {
			text := partsText(c.Parts)
			if c.Role == "model" {
				msgs = append(msgs, openai.AssistantMessage(text))
			} else {
				msgs = append(msgs, openai.UserMessage(text))
			}
		}

		modelID := req.Model
		if modelID == "" {
			modelID = m.modelName
		}
		params := openai.ChatCompletionNewParams{
			Model:    shared.ChatModel(modelID),
			Messages: msgs,
		}
		if req.Config != nil {
			if req.Config.Temperature != nil {
				params.Temperature = openai.Float(float64(*req.Config.Temperature))
			}
			if req.Config.MaxOutputTokens > 0 {
				params.MaxTokens = openai.Int(int64(req.Config.MaxOutputTokens))
			}
		}

		resp, err := m.client.Chat.Completions.New(ctx, params)
		if err != nil {
			yield(nil, fmt.Errorf("chat completion: %w", err))
			return
		}
		if len(resp.Choices) == 0 {
			yield(nil, fmt.Errorf("no choices in response"))
			return
		}

		yield(&model.LLMResponse{
			Content: &genai.Content{
				Role:  "model",
				Parts: []*genai.Part{{Text: resp.Choices[0].Message.Content}},
			},
			ModelVersion: modelID,
			UsageMetadata: &genai.GenerateContentResponseUsageMetadata{
				PromptTokenCount:     int32(resp.Usage.PromptTokens),
				CandidatesTokenCount: int32(resp.Usage.CompletionTokens),
				TotalTokenCount:      int32(resp.Usage.TotalTokens),
			},
			TurnComplete: true,
		}, nil)
	}
}
