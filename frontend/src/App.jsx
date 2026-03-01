import { useState, useEffect } from "react";
import axios from "axios";
import { API_BASE } from "./config";
import DocumentUpload from "./components/DocumentUpload";
import ChatWindow from "./components/ChatWindow";
import "./App.css";

export default function App() {
  const [activeDocument, setActiveDocument] = useState(null);
  const [quota, setQuota] = useState(null);

  const fetchQuota = async () => {
    try {
      const { data } = await axios.get(`${API_BASE}/quota/`);
      setQuota(data);
    } catch (err) {
      console.error("Failed to fetch quota:", err);
    }
  };

  useEffect(() => {
    fetchQuota();
    // Refresh quota every 30 seconds for real-time tracking
    const interval = setInterval(fetchQuota, 30000);
    return () => clearInterval(interval);
  }, []);

  // Refresh quota when a document is uploaded or chat occurs
  // (In a real app, you might use an event emitter or global state, 
  // but for now we'll rely on the interval and manual triggers if needed)

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-inner">
          <span className="logo">DocChat AI</span>
          <span className="subtitle">Ask questions about your PDFs</span>
        </div>
      </header>

      <main className="app-main">
        <aside className="sidebar">
          <DocumentUpload
            onDocumentReady={(doc) => {
              setActiveDocument(doc);
              fetchQuota(); // Refresh after upload
            }}
            activeDocument={activeDocument}
          />

          {quota && (
            <div className="quota-meter">
              <div className="quota-header">
                <span>Daily Requests</span>
                <span>{quota.total} / {quota.limit}</span>
              </div>
              <div className="quota-track">
                <div
                  className={`quota-bar ${quota.percent > 90 ? 'danger' : quota.percent > 70 ? 'warning' : ''}`}
                  style={{ width: `${quota.percent}%` }}
                />
              </div>
              <small className="quota-footer">
                {quota.remaining} remaining today
              </small>
            </div>
          )}
        </aside>

        <section className="chat-section">
          {activeDocument ? (
            <ChatWindow
              document={activeDocument}
              onBack={() => setActiveDocument(null)}
            />
          ) : (
            <div className="empty-state">
              <div className="empty-icon">AI</div>
              <h2>Upload a PDF to get started</h2>
              <p>Select a PDF from the sidebar, then ask any question about its content.</p>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
