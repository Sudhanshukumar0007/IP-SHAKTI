import { useState } from "react";
import { motion, AnimatePresence, useAnimation } from "framer-motion";
import { Eye, EyeOff } from "lucide-react";
import { Link } from "react-router-dom";
import AuthLayout from "./AuthLayout";

const LANGUAGES = ["English", "हिंदी", "தமிழ்", "বাংলা", "मराठी", "ગુજરાતી"];

function Field({ label, type="text", value, onChange, error, as="input", children, ...props }) {
  const [focused, setFocused] = useState(false);
  const Tag = as;

  return (
    <label className="block">
      <span className="text-xs tracking-wide text-[#5B5545]">{label}</span>
      <Tag
        type={as==="input" ? type : undefined}
        value={value}
        onChange={onChange}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        className="w-full bg-transparent py-2 text-[#1A1A16] outline-none placeholder:text-[#B9B29C]"
        {...props}
      >
        {children}
      </Tag>

      <div className="relative h-px bg-[#D8D0BA]">
        <motion.div
          className="absolute inset-0 origin-left bg-[#1F3D2B]"
          initial={false}
          animate={{scaleX:focused ? 1 : 0}}
          transition={{duration:.3,ease:"easeOut"}}
        />
      </div>

      {error && <span className="mt-1 block text-xs text-[#7A2E2E]">{error}</span>}
    </label>
  );
}

function PasswordField({ label, value, onChange, error }) {
  const [visible, setVisible] = useState(false);
  const [focused, setFocused] = useState(false);

  return (
    <label className="block">
      <span className="text-xs tracking-wide text-[#5B5545]">{label}</span>

      <div className="flex items-center">
        <input
          type={visible ? "text" : "password"}
          value={value}
          onChange={onChange}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          autoComplete={label === "Password" ? "current-password" : "new-password"}
          className="w-full bg-transparent py-2 text-[#1A1A16] outline-none"
        />
        <button
          type="button"
          onClick={() => setVisible(v=>!v)}
          className="text-[#9C9679] transition-colors hover:text-[#1F3D2B]"
          aria-label={visible ? "Hide password" : "Show password"}
        >
          {visible ? <EyeOff size={16}/> : <Eye size={16}/>}
        </button>
      </div>

      <div className="relative h-px bg-[#D8D0BA]">
        <motion.div
          className="absolute inset-0 origin-left bg-[#1F3D2B]"
          initial={false}
          animate={{scaleX:focused ? 1 : 0}}
          transition={{duration:.3,ease:"easeOut"}}
        />
      </div>

      {error && <span className="mt-1 block text-xs text-[#7A2E2E]">{error}</span>}
    </label>
  );
}

function ModeSwitch({ mode, onSwitch }) {
  return (
    <div className="relative mb-8 flex gap-6 border-b border-[#D8D0BA]">
      {["login","signup"].map(m => (
        <button
          key={m}
          type="button"
          onClick={() => onSwitch(m)}
          className={`relative pb-3 text-sm font-medium transition-colors ${mode===m ? "text-[#1F3D2B]" : "text-[#9C9679]"}`}
        >
          {m==="login" ? "Sign in" : "Create account"}
          {mode===m && (
            <motion.div
              layoutId="auth-tab-underline"
              className="absolute bottom-[-1px] left-0 right-0 h-[2px] bg-[#C97A2B]"
              transition={{type:"spring",stiffness:500,damping:40}}
            />
          )}
        </button>
      ))}
    </div>
  );
}

function SubmitButton({ children, loading }) {
  return (
    <motion.button
      type="submit"
      disabled={loading}
      whileHover={{y:-1}}
      whileTap={{scale:.98}}
      transition={{duration:.15}}
      className="mt-2 w-full rounded-md bg-[#C97A2B] py-3 font-medium tracking-wide text-[#F7F3E9] disabled:opacity-60"
    >
      {loading ? "Please wait…" : children}
    </motion.button>
  );
}

function AuthCard({ mode, onSwitchMode, onSubmit }) {
  const [form, setForm] = useState({
    name:"", org:"", email:"", language:LANGUAGES[0],
    password:"", confirm:"", remember:false, agree:false
  });
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [serverError, setServerError] = useState("");
  const controls = useAnimation();

  const set = key => e => setForm(f => ({
    ...f,
    [key]: e.target.type==="checkbox" ? e.target.checked : e.target.value
  }));

  const shake = () => controls.start({
    x:[0,-8,8,-6,6,0],
    transition:{duration:.4}
  });

  const validate = () => {
    const next = {};
    if (mode==="signup" && !form.name.trim()) next.name = "Enter your full name.";
    if (!form.email.trim()) next.email = "Enter your email.";
    else if (!/^\S+@\S+\.\S+$/.test(form.email)) next.email = "Enter a valid email.";
    if (!form.password) next.password = "Enter your password.";
    if (mode==="signup" && form.password.length < 8) next.password = "Use at least 8 characters.";
    if (mode==="signup" && form.confirm !== form.password) next.confirm = "Passwords don’t match.";
    if (mode==="signup" && !form.agree) next.agree = "Required to continue.";
    return next;
  };

  const handleSubmit = async e => {
    e.preventDefault();
    setServerError("");

    const next = validate();
    setErrors(next);

    if (Object.keys(next).length) {
      shake();
      return;
    }

    setLoading(true);
    try {
      await onSubmit?.({mode,...form});
    } catch (err) {
      setServerError(err?.message || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.div animate={controls}>
      <ModeSwitch mode={mode} onSwitch={onSwitchMode}/>

      <AnimatePresence mode="wait">
        <motion.form
          key={mode}
          onSubmit={handleSubmit}
          initial={{opacity:0,x:mode==="signup" ? 16 : -16}}
          animate={{opacity:1,x:0}}
          exit={{opacity:0,x:mode==="signup" ? -16 : 16}}
          transition={{duration:.25,ease:"easeOut"}}
          className="space-y-5"
        >
          {mode==="signup" && (
            <Field label="Full name" value={form.name} onChange={set("name")} error={errors.name} autoComplete="name"/>
          )}

          <Field label="Email" type="email" value={form.email} onChange={set("email")} error={errors.email} autoComplete="email"/>

          {mode==="signup" && (
            <>
              <Field label="Organisation (optional)" value={form.org} onChange={set("org")} autoComplete="organization"/>

              <Field label="Preferred language" as="select" value={form.language} onChange={set("language")}>
                {LANGUAGES.map(l => <option key={l} value={l}>{l}</option>)}
              </Field>
            </>
          )}

          <PasswordField label="Password" value={form.password} onChange={set("password")} error={errors.password}/>

          {mode==="signup" && (
            <PasswordField label="Confirm password" value={form.confirm} onChange={set("confirm")} error={errors.confirm}/>
          )}

          {mode==="login" ? (
            <div className="flex items-center justify-between text-xs text-[#5B5545]">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={form.remember} onChange={set("remember")} className="accent-[#1F3D2B]"/>
                Remember me
              </label>
              <Link to="/forgot-password" className="text-[#1F3D2B] hover:underline">Forgot password?</Link>
            </div>
          ) : (
            <label className="flex items-start gap-2 text-xs text-[#5B5545]">
              <input type="checkbox" checked={form.agree} onChange={set("agree")} className="mt-0.5 accent-[#1F3D2B]"/>
              <span>
                I agree to the{" "}
                <Link to="/terms" className="font-medium text-[#1F3D2B] underline">
                  Terms & Conditions
                </Link>{" "}
                and{" "}
                <Link to="/privacy" className="font-medium text-[#1F3D2B] underline">
                  Privacy & Data Handling Policy
                </Link>.
                {errors.agree && <span className="mt-1 block text-[#7A2E2E]">{errors.agree}</span>}
              </span>
            </label>
          )}

          {serverError && (
            <div className="rounded-lg border border-[#7A2E2E30] bg-[#7A2E2E08] p-3 text-xs text-[#7A2E2E]">
              {serverError}
            </div>
          )}

          <SubmitButton loading={loading}>
            {mode==="login" ? "Sign in" : "Create account"}
          </SubmitButton>

          <div className="pt-1 text-center text-[11px] text-[#9C9679]">
            {mode==="login" ? (
              <>New here? <button type="button" onClick={()=>onSwitchMode("signup")} className="font-semibold text-[#1F3D2B] underline">Create an account</button></>
            ) : (
              <>Already have an account? <button type="button" onClick={()=>onSwitchMode("login")} className="font-semibold text-[#1F3D2B] underline">Sign in</button></>
            )}
          </div>
        </motion.form>
      </AnimatePresence>
    </motion.div>
  );
}

export function LoginPage({onSubmit,onSwitchMode}) {
  return <AuthLayout><AuthCard mode="login" onSubmit={onSubmit} onSwitchMode={onSwitchMode}/></AuthLayout>;
}

export function SignupPage({onSubmit,onSwitchMode}) {
  return <AuthLayout><AuthCard mode="signup" onSubmit={onSubmit} onSwitchMode={onSwitchMode}/></AuthLayout>;
}
