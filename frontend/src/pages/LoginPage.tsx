import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api/client";

export function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api.post("/api/auth/login", { username, password });
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-fg">CentauriControl</h1>
          <p className="text-muted text-sm mt-1">3D Printer Dashboard</p>
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
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-surface2 border border-border rounded-lg px-3 py-2.5 text-sm text-fg focus:outline-none focus:border-accent transition-colors"
              autoComplete="current-password"
            />
          </div>
          {error && (
            <p className="text-red-400 text-xs">{error}</p>
          )}
          <button
            type="submit"
            disabled={loading || !password}
            className="w-full bg-accent hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium rounded-lg py-2.5 text-sm transition-colors"
          >
            {loading ? "Signing in…" : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}
