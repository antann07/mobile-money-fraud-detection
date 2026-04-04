import React from "react";
import { useTheme } from "../context/ThemeContext";

const OPTIONS = [
  { value: "default", icon: "☀️", title: "Default" },
  { value: "dark",    icon: "🌙", title: "Dark" },
  { value: "system",  icon: "💻", title: "System" },
];

function ThemeToggle() {
  const { preference, resolved, setTheme } = useTheme();

  // When the user is on "system" mode, append the actual resolved value
  // so they can see whether their OS is currently dark or light.
  // e.g. "💻 System (light)" or "💻 System (dark)"
  function titleFor(opt) {
    if (opt.value === "system" && preference === "system") {
      return `System (${resolved})`;
    }
    return opt.title;
  }

  return (
    <div className="theme-toggle" role="radiogroup" aria-label="Theme preference">
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          className={`theme-toggle-btn ${preference === opt.value ? "active" : ""}`}
          onClick={() => setTheme(opt.value)}
          title={titleFor(opt)}
          aria-label={titleFor(opt)}
          aria-checked={preference === opt.value}
          role="radio"
        >
          {opt.icon}
        </button>
      ))}
    </div>
  );
}

export default ThemeToggle;
