// ESLint for static/js, added 2026-09-08 with the first lint pass. Bug-class
// rules only, no style: the recommended set plus a few that catch a loop or a
// callback that cannot work. `npm run lint` (in this folder) must stay at ZERO.
import js from "@eslint/js";
import globals from "globals";
export default [
  js.configs.recommended,
  {
    files: ["**/*.js"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: { ...globals.browser, ...globals.es2024 },
    },
    rules: {
      // unused function ARGUMENTS are fine (event handlers); unused variables are dead code
      "no-unused-vars": ["warn", { args: "none", caughtErrors: "none", varsIgnorePattern: "^_" }],
      // a module-level `let` declared lower in the file and used inside a
      // function is legal and common here; only same-scope use-before-define counts
      "no-use-before-define": ["error", { functions: false, classes: false, variables: false }],
      "array-callback-return": "error",
      "no-self-compare": "error",
      "no-template-curly-in-string": "error",
      "no-unmodified-loop-condition": "error",
      "no-constructor-return": "error",
      "no-promise-executor-return": "error",
      "eqeqeq": ["warn", "smart"],
    },
  },
];
