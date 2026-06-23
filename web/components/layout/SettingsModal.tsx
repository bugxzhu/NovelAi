"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { LLMSettings } from "@/lib/types";
import { Button } from "@/components/ui/Button";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function SettingsModal({ open, onClose }: Props) {
  const [settings, setSettings] = useState<LLMSettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pingResult, setPingResult] = useState<string | null>(null);
  const [pinging, setPinging] = useState(false);

  useEffect(() => {
    if (!open) return;
    setSettings(null);
    setLoadError(null);
    setPingResult(null);
    api
      .getLLMSettings()
      .then(setSettings)
      .catch((e: unknown) => {
        setLoadError(e instanceof Error ? e.message : String(e));
      });
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const handlePing = async () => {
    setPinging(true);
    setPingResult(null);
    try {
      const resp = await api.pingLLM("ping");
      setPingResult(
        `✅ 连接成功 · 输入 ${resp.input_tokens} / 输出 ${resp.output_tokens} tokens · 返回: "${resp.text.slice(0, 40)}"`,
      );
    } catch (e) {
      const msg = e instanceof ApiError ? JSON.stringify(e.body) ?? e.message : (e as Error).message;
      setPingResult(`❌ 连接失败: ${msg}`);
    } finally {
      setPinging(false);
    }
  };

  const providerLabel =
    settings?.provider === "openai" ? "OpenAI 兼容" : settings?.provider === "claude" ? "Claude" : settings?.provider;

  const active =
    settings?.provider === "openai" ? settings.openai : settings?.provider === "claude" ? settings.anthropic : null;

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-panel border border-line rounded max-w-lg w-full max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-line">
          <h2 className="text-lg">⚙️ AI 设置</h2>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text text-xl leading-none"
            aria-label="关闭"
          >
            ×
          </button>
        </div>
        <div className="p-4 space-y-3">
          {loadError ? (
            <p className="text-red-500 text-sm">加载失败: {loadError}</p>
          ) : !settings ? (
            <p className="text-text-muted">加载中...</p>
          ) : (
            <>
              <div className="flex justify-between text-sm">
                <span className="text-text-muted">Provider</span>
                <span className="text-text font-bold">{providerLabel}</span>
              </div>

              {active && (
                <>
                  <div className="flex justify-between text-sm gap-2">
                    <span className="text-text-muted shrink-0">API Key</span>
                    <span className="text-text text-right truncate">
                      {active.api_key || "(未配置)"}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm gap-2">
                    <span className="text-text-muted shrink-0">Base URL</span>
                    <span className="text-text text-right truncate">
                      {active.base_url || "(官方默认)"}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm gap-2">
                    <span className="text-text-muted shrink-0">Model</span>
                    <span className="text-text text-right truncate">{active.model}</span>
                  </div>
                </>
              )}

              <div className="border-t border-line pt-3 mt-3">
                <div className="text-xs text-text-muted-bright mb-2">向量检索</div>
                <div className="flex justify-between text-sm">
                  <span className="text-text-muted">Embedding</span>
                  <span className="text-text">{settings.embedding.model}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-text-muted">维度</span>
                  <span className="text-text">{settings.embedding.dimensions}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-text-muted">Top-K / 阈值</span>
                  <span className="text-text">
                    {settings.retrieval.top_k} / {settings.retrieval.threshold}
                  </span>
                </div>
              </div>

              <div className="border-t border-line pt-3 mt-3">
                <Button variant="primary" onClick={handlePing} disabled={pinging}>
                  {pinging ? "⏳ 测试中..." : "🔌 测试连接"}
                </Button>
                {pingResult && (
                  <p className="text-sm mt-2 break-words text-text">{pingResult}</p>
                )}
              </div>

              <p className="text-xs text-text-muted border-t border-line pt-3">
                💡 设置在 <code className="bg-input px-1 rounded">.env</code>{" "}
                文件中配置。修改后重启后端生效。
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
