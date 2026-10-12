import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Field, FormError, Input } from "@/components/ui/form";
import { api } from "@/lib/api";
import { AuthLayout } from "./AuthLayout";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.post("/auth/password/reset/", { email });
      setSent(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthLayout title="Reset your password" footer={<Link to="/login" className="text-primary hover:underline">Back to sign in</Link>}>
      {sent ? (
        <p role="status" className="text-sm">If an account exists for <strong>{email}</strong>, a reset link is on its way. It may take a minute to arrive.</p>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-4">
          <FormError message={error} />
          <Field label="Email">{({ id }) => <Input id={id} type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />}</Field>
          <Button type="submit" loading={busy}>Send reset link</Button>
        </form>
      )}
    </AuthLayout>
  );
}
