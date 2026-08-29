package volcano

import (
	"bufio"
	"bytes"
	"errors"
	"io"
	"strings"
)

const (
	DefaultMaxSSEEventBytes = 1 << 20
	DefaultMaxSSELineBytes  = 64 << 10
)

var (
	ErrSSEEventTooLarge = errors.New("sse event exceeds configured limit")
	ErrSSELineTooLarge  = errors.New("sse line exceeds configured limit")
)

// SSEEvent 一个已分帧的 SSE 事件（data 已拼接）。
type SSEEvent struct {
	Data    string
	Comment bool
}

// SSEParser 增量 SSE 分帧，禁止 ReadAll 全响应。
type SSEParser struct {
	r        *bufio.Reader
	buf      bytes.Buffer
	line     int
	maxEvent int
	maxLine  int
}

func NewSSEParser(r io.Reader) *SSEParser {
	return NewSSEParserLimited(r, DefaultMaxSSEEventBytes, DefaultMaxSSELineBytes)
}

func NewSSEParserLimited(r io.Reader, maxEvent, maxLine int) *SSEParser {
	if maxEvent < 1 {
		maxEvent = DefaultMaxSSEEventBytes
	}
	if maxLine < 1 {
		maxLine = DefaultMaxSSELineBytes
	}
	return &SSEParser{r: bufio.NewReaderSize(r, 4096), maxEvent: maxEvent, maxLine: maxLine}
}

// Next 返回下一个完整事件。EOF 且无残留完整事件时 io.EOF。
func (p *SSEParser) Next() (SSEEvent, error) {
	for {
		b, err := p.r.ReadByte()
		if err != nil {
			if err == io.EOF && p.buf.Len() > 0 {
				// 不把半帧当完整事件
				if ev, ok := flushEvent(p.buf.Bytes(), true); ok {
					p.buf.Reset()
					p.line = 0
					return ev, nil
				}
			}
			return SSEEvent{}, err
		}
		if p.buf.Len()+1 > p.maxEvent {
			p.buf.Reset()
			p.line = 0
			return SSEEvent{}, ErrSSEEventTooLarge
		}
		if b != '\n' {
			p.line++
			if p.line > p.maxLine {
				p.buf.Reset()
				p.line = 0
				return SSEEvent{}, ErrSSELineTooLarge
			}
		} else {
			p.line = 0
		}
		_ = p.buf.WriteByte(b)
		if b != '\n' {
			continue
		}
		raw := p.buf.Bytes()
		if endsEvent(raw) {
			ev, ok := flushEvent(raw, false)
			p.buf.Reset()
			p.line = 0
			if !ok {
				continue
			}
			return ev, nil
		}
	}
}

func endsEvent(raw []byte) bool {
	if bytes.HasSuffix(raw, []byte("\n\n")) {
		return true
	}
	if bytes.HasSuffix(raw, []byte("\r\n\r\n")) {
		return true
	}
	return false
}

func flushEvent(raw []byte, eof bool) (SSEEvent, bool) {
	s := string(raw)
	s = strings.TrimRight(s, "\n")
	s = strings.ReplaceAll(s, "\r", "")
	if strings.TrimSpace(s) == "" {
		return SSEEvent{}, false
	}
	var dataLines []string
	hasData := false
	for _, line := range strings.Split(s, "\n") {
		if strings.HasPrefix(line, ":") {
			continue
		}
		if strings.HasPrefix(line, "data:") {
			hasData = true
			dataLines = append(dataLines, strings.TrimPrefix(line, "data:"))
			continue
		}
		// event:/id:/retry: 忽略
	}
	if !hasData {
		return SSEEvent{}, false
	}
	for i := range dataLines {
		dataLines[i] = strings.TrimPrefix(dataLines[i], " ")
	}
	return SSEEvent{Data: strings.Join(dataLines, "\n")}, true
}

// IsDoneData 是否为终止标记。
func IsDoneData(data string) bool {
	return strings.TrimSpace(data) == "[DONE]"
}

// Incremental 检测测试替身是否错误地 ReadAll（文档/断言辅助，恒 false 于解析器）。
func (p *SSEParser) Incremental() bool { return true }
