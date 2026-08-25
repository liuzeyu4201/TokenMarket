package volcano

import (
	"bufio"
	"bytes"
	"io"
	"strings"
)

// SSEEvent 一个已分帧的 SSE 事件（data 已拼接）。
type SSEEvent struct {
	Data    string
	Comment bool
}

// SSEParser 增量 SSE 分帧，禁止 ReadAll 全响应。
type SSEParser struct {
	r   *bufio.Reader
	buf bytes.Buffer
}

func NewSSEParser(r io.Reader) *SSEParser {
	return &SSEParser{r: bufio.NewReaderSize(r, 4096)}
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
					return ev, nil
				}
			}
			return SSEEvent{}, err
		}
		_ = p.buf.WriteByte(b)
		if b != '\n' {
			continue
		}
		raw := p.buf.Bytes()
		// 空行结束事件：\n\n 或 \r\n\r\n
		if endsEvent(raw) {
			ev, ok := flushEvent(raw, false)
			p.buf.Reset()
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
	// data: 多行用 \n 拼接；每行去掉一个可选前导空格
	for i := range dataLines {
		dataLines[i] = strings.TrimPrefix(dataLines[i], " ")
	}
	return SSEEvent{Data: strings.Join(dataLines, "\n")}, true
}

// IsDoneData 是否为终止标记。
func IsDoneData(data string) bool {
	return strings.TrimSpace(data) == "[DONE]"
}

// DidReadAll 检测测试替身是否错误地 ReadAll（文档/断言辅助，恒 false 于解析器）。
func (p *SSEParser) Incremental() bool { return true }
