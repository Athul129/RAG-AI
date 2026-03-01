import { useState, useRef, useEffect } from "react";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import axios from "axios";
import { API_BASE } from "../config";

function Message({ msg }) {
    const isUser = msg.role === "user";
    return (
        <div className={`message ${isUser ? "message-user" : "message-ai"}`}>
            <div className="message-avatar">{isUser ? "You" : "AI"}</div>
            <div className="message-body">
                {isUser ? (
                    <p className="message-text">{msg.content}</p>
                ) : (
                    <div className="message-text ai-content">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                        {msg.streaming && <span className="cursor-blink">▍</span>}
                    </div>
                )}
                {msg.sources?.length > 0 && (
                    <details className="sources">
                        <summary>View sources ({msg.sources.length})</summary>
                        {msg.sources.map((s, i) => (
                            <blockquote key={i} className="source-item">
                                <strong>Page {s.page + 1}:</strong> {s.snippet}...
                            </blockquote>
                        ))}
                    </details>
                )}
            </div>
        </div>
    );
}

export default function ChatWindow({ document, onBack }) {
    const introMessage = document.is_processed
        ? `I've loaded "${document.title}". Ask me anything about it!`
        : `"${document.title}" is still processing. You can ask questions once it is ready.`;

    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const [fetchingHistory, setFetchingHistory] = useState(false);
    const bottomRef = useRef(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    const fetchHistory = async () => {
        if (!document.id) return;
        setFetchingHistory(true);
        try {
            const { data } = await axios.get(`${API_BASE}/documents/history/${document.id}/`);
            const history = data.map(msg => ([
                { role: "user", content: msg.question },
                { role: "ai", content: msg.answer }
            ])).flat();

            setMessages([
                { role: "ai", content: introMessage },
                ...history
            ]);
        } catch (err) {
            console.error("Failed to fetch history:", err);
            setMessages([{ role: "ai", content: introMessage }]);
        } finally {
            setFetchingHistory(false);
        }
    };

    useEffect(() => {
        fetchHistory();
        setInput("");
    }, [document.id, document.is_processed, document.title]);

    const clearHistory = async () => {
        if (!window.confirm("Are you sure you want to clear chat history for this document?")) return;
        try {
            await axios.delete(`${API_BASE}/documents/history/${document.id}/`);
            setMessages([{ role: "ai", content: introMessage }]);
        } catch (err) {
            alert("Failed to clear history.");
        }
    };

    const sendMessage = async () => {
        const question = input.trim();
        if (!question || loading || !document.is_processed) return;

        setMessages((prev) => [...prev, { role: "user", content: question }]);
        setInput("");
        setLoading(true);

        // Add an empty streaming AI message placeholder
        const aiMsgIndex = (prev) => prev.length; // will be messages.length after user msg
        setMessages((prev) => [
            ...prev,
            { role: "ai", content: "", streaming: true, sources: [] },
        ]);

        try {
            const response = await fetch(`${API_BASE}/documents/stream/`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ document_id: document.id, question }),
            });

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.error || `HTTP ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop(); // keep incomplete last line

                for (const line of lines) {
                    if (line.startsWith("data: ")) {
                        const token = line.slice(6); // strip "data: "
                        setMessages((prev) => {
                            const updated = [...prev];
                            const last = updated[updated.length - 1];
                            if (last?.role === "ai") {
                                updated[updated.length - 1] = {
                                    ...last,
                                    content: last.content + token,
                                };
                            }
                            return updated;
                        });
                    } else if (line.startsWith("event: sources")) {
                        // next line will be data: [...]
                    } else if (line.startsWith("data: ") && buffer.includes("sources")) {
                        // handled above
                    } else if (line.startsWith("data: ") && line.includes("[")) {
                        // could be sources data; skip — handled by event: sources
                    }

                    // Handle sources event data
                    if (line.startsWith("data: [") || line.startsWith("data: []")) {
                        try {
                            const sources = JSON.parse(line.slice(6));
                            if (Array.isArray(sources)) {
                                setMessages((prev) => {
                                    const updated = [...prev];
                                    const last = updated[updated.length - 1];
                                    if (last?.role === "ai") {
                                        updated[updated.length - 1] = { ...last, sources };
                                    }
                                    return updated;
                                });
                            }
                        } catch (_) { }
                    }
                }
            }

            // Mark streaming as done
            setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last?.role === "ai") {
                    updated[updated.length - 1] = { ...last, streaming: false };
                }
                return updated;
            });

        } catch (err) {
            setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last?.role === "ai" && last.streaming) {
                    updated[updated.length - 1] = {
                        role: "ai",
                        content: err.message ?? "Sorry, something went wrong.",
                        streaming: false,
                    };
                } else {
                    updated.push({
                        role: "ai",
                        content: err.message ?? "Sorry, something went wrong.",
                    });
                }
                return updated;
            });
        } finally {
            setLoading(false);
        }
    };

    const onKeyDown = (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };

    return (
        <div className="chat-window">
            <div className="chat-header">
                <div className="header-info">
                    <button className="back-btn" onClick={() => onBack()} title="Go Back">
                        ←
                    </button>
                    <span>Chatting with:</span>
                    <strong>{document.title}</strong>
                    {!document.is_processed && <span className="processing-pill">Processing</span>}
                </div>
                <button
                    className="clear-history-btn"
                    onClick={clearHistory}
                    disabled={messages.length <= 1 || !document.is_processed}
                    title="Clear Chat History"
                >
                    Clear Chat
                </button>
            </div>

            <div className="messages-container">
                {messages.map((msg, i) => (
                    <Message key={i} msg={msg} />
                ))}

                {loading && messages[messages.length - 1]?.content === "" && (
                    <div className="message message-ai">
                        <div className="message-avatar">AI</div>
                        <div className="message-body typing">
                            <span /><span /><span />
                        </div>
                    </div>
                )}

                <div ref={bottomRef} />
            </div>

            <div className="input-area">
                <textarea
                    className="chat-input"
                    rows={2}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={onKeyDown}
                    placeholder={
                        document.is_processed
                            ? "Ask a question... (Enter to send)"
                            : "This document is still processing."
                    }
                    disabled={loading || !document.is_processed}
                />
                <button
                    className="send-btn"
                    onClick={sendMessage}
                    disabled={!input.trim() || loading || !document.is_processed}
                >
                    {loading ? "..." : "Send"}
                </button>
            </div>
        </div>
    );
}
