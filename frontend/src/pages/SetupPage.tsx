import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api/client";

export function SetupPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    setLoading(true);
    try {
      await api.post("/api/auth/setup", { username, password });
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Setup failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-fg">Welcome to CentauriControl</h1>
          <p className="text-muted text-sm mt-1">Set up your administrator account</p>
        </div>
        <form
          onSubmit={handleSubmit}
          className="bg-surface border border-border rounded-xl p-8 space-y-5"
        >
          <div>
            <label className="block text-xs font-medium text-muted mb-1.5">
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-surface2 border border-border rounded-lg px-3 py-2.5 text-sm text-fg focus:outline-none focus:border-accent transition-colors"
              autoComplete="username"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted mb-1.5">
              Password <span className="text-muted font-normal">(min 8 characters)</span>
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-surface2 border border-border rounded-lg px-3 py-2.5 text-sm text-fg focus:outline-none focus:border-accent transition-colors"
              autoComplete="new-password"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted mb-1.5">
              Confirm Password
            </label>
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="w-full bg-surface2 border border-border rounded-lg px-3 py-2.5 text-sm text-fg focus:outline-none focus:border-accent transition-colors"
              autoComplete="new-password"
            />
          </div>
          {error && (
            <p className="text-red-400 text-xs">{error}</p>
          )}
          <button
            type="submit"
            disabled={loading || !password || !confirm}
            className="w-full bg-accent hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium rounded-lg py-2.5 text-sm transition-colors"
          >
            {loading ? "Creating account…" : "Create Account"}
          </button>
        </form>
      </div>
    </div>
  );
}
