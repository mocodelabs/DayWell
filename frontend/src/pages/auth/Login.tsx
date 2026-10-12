import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";
import { Button } from "@/components/ui/Button";
import { Field, FormError, Input } from "@/components/ui/form";
import { keys } from "@/hooks/queries";
import { api, applyServerErrors } from "@/lib/api";
import type { Me } from "@/lib/types";
import { AuthLayout } from "./AuthLayout";

const schema = z.object({
  email: z.email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});
type Values = z.infer<typeof schema>;

export default function Login() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState("");
  const { register, handleSubmit, setError: setFieldError, formState: { errors, isSubmitting } } = useForm<Values>({ resolver: zodResolver(schema) });

  const onSubmit = async (v: Values) => {
    setError("");
    try {
      const me = await api.post<Me>("/auth/login/", v);
      qc.setQueryData(keys.me, me);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(me.preferences.onboarding_completed ? from || "/" : "/welcome", { replace: true });
    } catch (e) {
      setError(applyServerErrors(e, setFieldError, ["email", "password"]));
    }
  };

  return (
    <AuthLayout title="Welcome back" subtitle="Sign in to see your day." footer={<>New to DayWell? <Link className="font-medium text-primary hover:underline" to="/register">Create an account</Link></>}>
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
        <FormError message={error} />
        <Field label="Email" error={errors.email?.message}>
          {({ id, describedBy, invalid }) => <Input id={id} type="email" autoComplete="email" aria-describedby={describedBy} aria-invalid={invalid} {...register("email")} />}
        </Field>
        <Field label="Password" error={errors.password?.message}>
          {({ id, describedBy, invalid }) => <Input id={id} type="password" autoComplete="current-password" aria-describedby={describedBy} aria-invalid={invalid} {...register("password")} />}
        </Field>
        <Button type="submit" size="lg" loading={isSubmitting}>Sign in</Button>
        <Link to="/forgot-password" className="text-center text-sm text-primary hover:underline">Forgot your password?</Link>
      </form>
    </AuthLayout>
  );
}
