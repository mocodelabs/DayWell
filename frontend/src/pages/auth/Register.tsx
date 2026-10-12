import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { z } from "zod";
import { Button } from "@/components/ui/Button";
import { Field, FormError, Input } from "@/components/ui/form";
import { keys } from "@/hooks/queries";
import { api, applyServerErrors } from "@/lib/api";
import type { Me } from "@/lib/types";
import { AuthLayout } from "./AuthLayout";

const schema = z.object({
  display_name: z.string().trim().max(80),
  email: z.email("Enter a valid email address."),
  password: z.string().min(10, "Use at least 10 characters.").max(128),
});
type Values = z.infer<typeof schema>;

export default function Register() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [verifyEmail, setVerifyEmail] = useState<string | null>(null);
  const { register, handleSubmit, setError: setFieldError, formState: { errors, isSubmitting } } = useForm<Values>({ resolver: zodResolver(schema) });

  const onSubmit = async (v: Values) => {
    setError("");
    try {
      const time_zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
      const res = await api.post<Me | { verification_required: true; email: string }>("/auth/register/", { ...v, time_zone });
      if ("verification_required" in res) {
        setVerifyEmail(res.email);
        return;
      }
      qc.setQueryData(keys.me, res);
      navigate("/welcome", { replace: true });
    } catch (e) {
      setError(applyServerErrors(e, setFieldError, ["display_name", "email", "password"]));
    }
  };

  if (verifyEmail) {
    return (
      <AuthLayout title="Check your inbox" subtitle={`We sent a confirmation link to ${verifyEmail}.`}>
        <p className="text-sm text-muted">Open the link to confirm your email, then sign in.</p>
        <Link to="/login" className="mt-4 inline-block font-medium text-primary hover:underline">Go to sign in</Link>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Create your account" subtitle="A calm place for your plans, reminders and routines." footer={<>Already have an account? <Link className="font-medium text-primary hover:underline" to="/login">Sign in</Link></>}>
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
        <FormError message={error} />
        <Field label="What should we call you?" optional error={errors.display_name?.message}>
          {({ id, invalid }) => <Input id={id} autoComplete="given-name" aria-invalid={invalid} {...register("display_name")} />}
        </Field>
        <Field label="Email" error={errors.email?.message}>
          {({ id, describedBy, invalid }) => <Input id={id} type="email" autoComplete="email" aria-describedby={describedBy} aria-invalid={invalid} {...register("email")} />}
        </Field>
        <Field label="Password" error={errors.password?.message} hint="At least 10 characters. A short phrase works well.">
          {({ id, describedBy, invalid }) => <Input id={id} type="password" autoComplete="new-password" aria-describedby={describedBy} aria-invalid={invalid} {...register("password")} />}
        </Field>
        <Button type="submit" size="lg" loading={isSubmitting}>Create account</Button>
        <p className="text-center text-xs text-muted">Your schedule, habits and reflections are private by default. We never sell your data.</p>
      </form>
    </AuthLayout>
  );
}
