import { useEffect, useState, useRef } from "react";
import axios from "axios";
import { API_BASE } from "../config";

const POLL_INTERVAL_MS = 3000;

export default function DocumentUpload({ onDocumentReady, activeDocument }) {
    const [documents, setDocuments] = useState([]);
    const [uploading, setUploading] = useState(false);
    const [dragOver, setDragOver] = useState(false);
    const [error, setError] = useState("");
    const fileInputRef = useRef(null);
    const didInitialFetch = useRef(false);

    const fetchDocuments = async () => {
        try {
            const { data } = await axios.get(`${API_BASE}/documents/upload/`);
            setDocuments(data);
            setError("");

            if (activeDocument) {
                const refreshed = data.find((doc) => doc.id === activeDocument.id);
                if (refreshed) onDocumentReady(refreshed);
            }
        } catch {
            setError("Failed to load documents.");
        }
    };

    useEffect(() => {
        if (didInitialFetch.current) return;
        didInitialFetch.current = true;
        fetchDocuments();
    }, []);

    useEffect(() => {
        if (!documents.some((doc) => !doc.is_processed)) return undefined;

        const intervalId = setInterval(fetchDocuments, POLL_INTERVAL_MS);
        return () => clearInterval(intervalId);
    }, [documents, activeDocument?.id]);

    const handleFile = async (file) => {
        if (!file || file.type !== "application/pdf") {
            setError("Please select a valid PDF file.");
            return;
        }
        setError("");
        setUploading(true);

        const formData = new FormData();
        formData.append("title", file.name.replace(".pdf", ""));
        formData.append("file", file);

        try {
            const { data } = await axios.post(`${API_BASE}/documents/upload/`, formData, {
                headers: { "Content-Type": "multipart/form-data" },
            });
            setDocuments((prev) => [data, ...prev]);
            onDocumentReady(data);
        } catch (err) {
            setError(err.response?.data?.error ?? "Upload failed. Please try again.");
        } finally {
            setUploading(false);
        }
    };

    const onInputChange = (e) => handleFile(e.target.files[0]);

    const onDrop = (e) => {
        e.preventDefault();
        setDragOver(false);
        handleFile(e.dataTransfer.files[0]);
    };

    const onDocumentClick = (doc) => {
        if (!doc.is_processed) {
            setError("This document is still being processed.");
            return;
        }
        setError("");
        onDocumentReady(doc);
    };

    const deleteDocument = async (e, docId) => {
        e.stopPropagation();
        if (!window.confirm("Are you sure you want to delete this document and all its chat history?")) return;

        try {
            await axios.delete(`${API_BASE}/documents/${docId}/`);
            setDocuments((prev) => prev.filter((doc) => doc.id !== docId));
            if (activeDocument?.id === docId) {
                onDocumentReady(null);
            }
        } catch {
            setError("Failed to delete document.");
        }
    };

    return (
        <div className="upload-panel">
            <h3 className="panel-title">Documents</h3>

            <div
                className={`drop-zone ${dragOver ? "drag-over" : ""} ${uploading ? "uploading" : ""}`}
                onClick={() => !uploading && fileInputRef.current.click()}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={onDrop}
            >
                <input
                    ref={fileInputRef}
                    type="file"
                    accept="application/pdf"
                    onChange={onInputChange}
                    style={{ display: "none" }}
                />
                {uploading ? (
                    <>
                        <div className="spinner" />
                        <p>Processing PDF...</p>
                    </>
                ) : (
                    <>
                        <span className="drop-icon">[PDF]</span>
                        <p><strong>Click or drag</strong> a PDF here</p>
                    </>
                )}
            </div>

            {error && <p className="error-msg">{error}</p>}

            {documents.length > 0 && (
                <ul className="doc-list">
                    {documents.map((doc) => (
                        <li
                            key={doc.id}
                            className={`doc-item ${activeDocument?.id === doc.id ? "active" : ""}`}
                            onClick={() => onDocumentClick(doc)}
                        >
                            <span className="doc-icon">[DOC]</span>
                            <span className="doc-title">{doc.title}</span>
                            <span className={`badge ${doc.is_processed ? "badge-ready" : "badge-processing"}`}>
                                {doc.is_processed ? "Ready" : "Processing"}
                            </span>
                            <button
                                className="doc-delete-btn"
                                onClick={(e) => deleteDocument(e, doc.id)}
                                title="Delete Document"
                            >
                                ×
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}
