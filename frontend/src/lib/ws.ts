"use client";

type EventHandler = (data: unknown) => void;

class TradingWebSocket {
  private ws: WebSocket | null = null;
  private handlers: Map<string, EventHandler[]> = new Map();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private userId: string | null = null;

  connect(userId: string, token: string) {
    this.userId = userId;
    const wsBase = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";
    const url = `${wsBase}/ws/${userId}`;

    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      console.log("[WS] Connected");
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = null;
      }
      // Send auth as first message (token never travels in URL)
      this.ws?.send(JSON.stringify({ type: "auth", token }));
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        const { type, data } = msg;
        const handlers = this.handlers.get(type) || [];
        handlers.forEach((h) => h(data));
        // Also call wildcard handlers
        const wildcardHandlers = this.handlers.get("*") || [];
        wildcardHandlers.forEach((h) => h(msg));
      } catch (e) {
        console.error("[WS] Failed to parse message:", e);
      }
    };

    this.ws.onclose = (event) => {
      console.log("[WS] Disconnected:", event.code);
      if (event.code !== 1000 && this.userId) {
        // Auto-reconnect after 3s
        this.reconnectTimer = setTimeout(() => {
          const t = localStorage.getItem("access_token");
          if (t && this.userId) this.connect(this.userId, t);
        }, 3000);
      }
    };

    this.ws.onerror = (err) => {
      console.error("[WS] Error:", err);
    };
  }

  on(eventType: string, handler: EventHandler) {
    const existing = this.handlers.get(eventType) || [];
    this.handlers.set(eventType, [...existing, handler]);
    return () => this.off(eventType, handler);
  }

  off(eventType: string, handler: EventHandler) {
    const existing = this.handlers.get(eventType) || [];
    this.handlers.set(
      eventType,
      existing.filter((h) => h !== handler)
    );
  }

  disconnect() {
    this.userId = null;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.ws) {
      this.ws.close(1000, "User disconnected");
      this.ws = null;
    }
  }

  get isConnected() {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

export const tradingWS = new TradingWebSocket();
