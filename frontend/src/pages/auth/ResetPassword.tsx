import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Field, FormError, Input } from "@/components/ui/form";
import { ApiError, api } from "@/lib/api";
import { AuthLayout } from "./AuthLayout";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.post("/auth/password/reset/confirm/", { uid: params.get("uid"), token: params.get("token"), new_password: password });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? (err.fields.new_password?.join(" ") || err.message) : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthLayout title="Choose a new password">
      {done ? (
        <div role="status">
          <p className="text-sm">Your password has been changed. You've been signed out everywhere for safety.</p>
          <Link to="/login" className="mt-4 inline-block font-medium text-primary hover:underline">Sign in</Link>
        </div>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-4">
          <FormError message={error} />
          <Field label="New password" hint="At least 10 characters.">
            {({ id, describedBy }) => <Input id={id} type="password" autoComplete="new-password" required minLength={10} aria-describedby={describedBy} value={password} onChange={(e) => setPassword(e.target.value)} />}
          </Field>
          <Button type="submit" loading={busy}>Save password</Button>
        </form>
      )}
    </AuthLayout>
  );
}
