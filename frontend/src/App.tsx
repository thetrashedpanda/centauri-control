import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { LoginPage } from "@/pages/LoginPage";
import { SetupPage } from "@/pages/SetupPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { api } from "@/api/client";

interface AuthStatus {
  auth_enabled: boolean;
  has_password: boolean;
  authenticated: boolean;
}

function AuthGate({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<AuthStatus>("/api/auth/status")
      .then(setStatus)
      .catch(() => setStatus({ auth_enabled: false, has_password: false, authenticated: true }))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bg">
        <div className="text-muted text-sm">Loading…</div>
      </div>
    );
  }

  if (!status) return null;

  // First time setup
  if (status.auth_enabled && !status.has_password) {
    return <Navigate to="/setup" replace />;
  }

  // Need to log in
  if (status.auth_enabled && !status.authenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/setup" element={<SetupPage />} />
        <Route
          path="/dashboard"
          element={
            <AuthGate>
              <DashboardPage />
            </AuthGate>
          }
        />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
