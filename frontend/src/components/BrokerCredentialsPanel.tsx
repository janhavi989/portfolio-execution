import { useEffect, useState, useCallback } from "react";
import toast from "react-hot-toast";
import { brokerApi } from "../api/client";
import type { BrokerCredentials } from "../types";
import { BROKER_DISPLAY } from "../types";
import type { BrokerName } from "../types";

interface Props {
  broker: string;
  isConnected: boolean;
}

interface FieldRow {
  label: string;
  key: keyof BrokerCredentials;
  sensitive: boolean;
  description: string;
}

const FIELDS: FieldRow[] = [
  { label: "API Key",        key: "api_key",       sensitive: false, description: "Public identifier for your Kite Connect app" },
  { label: "API Secret",     key: "api_secret",    sensitive: true,  description: "Secret used to compute the auth checksum" },
  { label: "Client ID",      key: "client_id",     sensitive: false, description: "Your broker user/client ID" },
  { label: "Request Token",  key: "request_token", sensitive: true,  description: "One-time token from OAuth redirect (Zerodha/Fyers/Upstox)" },
  { label: "Access Token",   key: "access_token",  sensitive: true,  description: "Live session token used in every API call" },
  { label: "Refresh Token",  key: "refresh_token", sensitive: true,  description: "Used to renew the access token without re-login" },
  { label: "TOTP Secret",    key: "totp_secret",   sensitive: true,  description: "Base32 secret for TOTP 2FA (AngelOne)" },
  { label: "Password",       key: "password",      sensitive: true,  description: "Login password (AngelOne)" },
  { label: "Expires At",     key: "expires_at",    sensitive: false, description: "When the current session token expires" },
];

function maskValue(val: string): string {
  if (val.length <= 8) return "•".repeat(val.length);
  return val.slice(0, 4) + "•".repeat(Math.min(val.length - 8, 20)) + val.slice(-4);
}

function CredentialRow({
  field,
  value,
}: {
  field: FieldRow;
  value: string | null;
}) {
  const [revealed, setRevealed] = useState(false);

  const handleCopy = () => {
    if (!value) return;
    navigator.clipboard.writeText(value);
    toast.success(`${field.label} copied!`);
  };

  if (!value) {
    return (
      <div className="flex items-center justify-between py-2.5 border-b border-slate-800/60 last:border-0">
        <div>
          <p className="text-xs font-medium text-slate-400">{field.label}</p>
          <p className="text-xs text-slate-600 mt-0.5">{field.description}</p>
        </div>
        <span className="text-xs text-slate-600 italic">not set</span>
      </div>
    );
  }

  const display = field.sensitive && !revealed ? maskValue(value) : value;

  return (
    <div className="py-2.5 border-b border-slate-800/60 last:border-0">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium text-slate-300">{field.label}</p>
          <p className="text-xs text-slate-500 mt-0.5">{field.description}</p>
          <p className="text-xs font-mono text-indigo-300 mt-1.5 break-all leading-relaxed">
            {display}
          </p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0 mt-0.5">
          {field.sensitive && (
            <button
              onClick={() => setRevealed((r) => !r)}
              className="text-xs text-slate-500 hover:text-slate-300 px-2 py-1 rounded border border-slate-700 hover:border-slate-600 transition"
              title={revealed ? "Hide" : "Reveal"}
            >
              {revealed ? "🙈" : "👁"}
            </button>
          )}
          <button
            onClick={handleCopy}
            className="text-xs text-slate-500 hover:text-indigo-400 px-2 py-1 rounded border border-slate-700 hover:border-indigo-500/50 transition"
            title="Copy to clipboard"
          >
            📋
          </button>
        </div>
      </div>
    </div>
  );
}

export default function BrokerCredentialsPanel({ broker, isConnected }: Props) {
  const [creds, setCreds] = useState<BrokerCredentials | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const fetchCreds = useCallback(async () => {
    if (!isConnected || !broker) return;
    setLoading(true);
    setError(null);
    try {
      const res = await brokerApi.credentials(broker);
      setCreds(res.data);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Failed to load credentials";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [broker, isConnected]);

  useEffect(() => {
    if (open && !creds) fetchCreds();
  }, [open, creds, fetchCreds]);

  // Reset when broker changes
  useEffect(() => {
    setCreds(null);
    setOpen(false);
    setError(null);
  }, [broker]);

  if (!isConnected) return null;

  const brokerLabel = BROKER_DISPLAY[broker as BrokerName] ?? broker;

  return (
    <div className="border-t border-slate-800">
      {/* Collapsible header */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-800/40 transition text-left"
      >
        <div className="flex items-center gap-2">
          <span className="text-base">🔑</span>
          <span className="text-sm font-semibold text-white">Saved Credentials</span>
          <span className="text-xs text-slate-500">({brokerLabel})</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-full">
            Sensitive
          </span>
          <span className="text-slate-500 text-sm">{open ? "▲" : "▼"}</span>
        </div>
      </button>

      {open && (
        <div className="px-4 pb-4">
          {/* Warning banner */}
          <div className="mb-3 flex items-start gap-2 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2">
            <span className="text-amber-400 mt-0.5">⚠️</span>
            <p className="text-xs text-amber-400">
              These credentials are stored in your local SQLite database. Never share them.
              Sensitive fields are masked by default — click 👁 to reveal.
            </p>
          </div>

          {/* Loading */}
          {loading && (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-14 bg-slate-800/60 rounded-lg animate-pulse" />
              ))}
            </div>
          )}

          {/* Error */}
          {error && !loading && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-xs text-red-400">
              ⚠️ {error}
            </div>
          )}

          {/* Credential rows */}
          {creds && !loading && (
            <>
              {/* Session meta */}
              <div className="mb-3 flex items-center gap-4 text-xs text-slate-500">
                <span>
                  Connected:{" "}
                  <span className="text-slate-300">
                    {new Date(creds.created_at).toLocaleString()}
                  </span>
                </span>
                <span>
                  Updated:{" "}
                  <span className="text-slate-300">
                    {new Date(creds.updated_at).toLocaleString()}
                  </span>
                </span>
              </div>

              <div className="bg-slate-900 rounded-xl border border-slate-700 px-4 py-1">
                {FIELDS.map((field) => (
                  <CredentialRow
                    key={field.key}
                    field={field}
                    value={creds[field.key] as string | null}
                  />
                ))}
              </div>

              <button
                onClick={fetchCreds}
                className="mt-3 w-full text-xs text-slate-500 hover:text-slate-300 py-1.5 rounded-lg border border-slate-800 hover:border-slate-700 transition"
              >
                ↻ Refresh
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}


