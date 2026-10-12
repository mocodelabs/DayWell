import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import { AuthLayout } from "./AuthLayout";

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const [state, setState] = useState<"working" | "ok" | "error">("working");
  const [message, setMessage] = useState("");
  useEffect(() => {
    api.post("/auth/email/verify/", { uid: params.get("uid"), token: params.get("token") })
      .then(() => setState("ok"))
      .catch((e: Error) => {
        setState("error");
        setMessage(e.message);
      });
  }, [params]);
  return (
    <AuthLayout title={state === "ok" ? "Email confirmed" : state === "error" ? "We couldn't confirm that link" : "Confirming…"}>
      <p role="status" className="text-sm">{state === "ok" ? "Thank you — your email address is confirmed." : state === "error" ? message : "One moment…"}</p>
      <Link to="/" className="mt-4 inline-block font-medium text-primary hover:underline">Continue to DayWell</Link>
    </AuthLayout>
  );
}
