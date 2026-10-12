/** Windows 资源管理器风格文件夹图标（复刻自 docmgr 文档空间目录树，EAI-CUSTOM）。 */

export function WindowsFolder({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M1.5 6.5C1.5 5.4 2.4 4.5 3.5 4.5h4.7c.6 0 1.2.25 1.62.69L11.06 6.5H18.5c1.1 0 2 .9 2 2V10H3.5C2.4 10 1.5 9.1 1.5 8V6.5z"
        fill="#E6A106"
      />
      <path
        d="M1.5 9.5C1.5 8.4 2.4 7.5 3.5 7.5h17c1.1 0 2 .9 2 2v8c0 1.1-.9 2-2 2h-17c-1.1 0-2-.9-2-2v-8z"
        fill="#FFC83D"
      />
      <path
        d="M1.5 9.5C1.5 8.4 2.4 7.5 3.5 7.5h17c1.1 0 2 .9 2 2V11H1.5V9.5z"
        fill="#FFD86B"
      />
    </svg>
  );
}

export function WindowsFolderOpen({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M1.5 6.5C1.5 5.4 2.4 4.5 3.5 4.5h4.7c.6 0 1.2.25 1.62.69L11.06 6.5H18.5c1.1 0 2 .9 2 2V10H3.5C2.4 10 1.5 9.1 1.5 8V6.5z"
        fill="#E6A106"
      />
      <path
        d="M3 10.5h18l-1.2 7.2c-.15.9-.93 1.55-1.84 1.55H4.04c-.91 0-1.69-.65-1.84-1.55L3 10.5z"
        fill="#FFE082"
      />
      <path
        d="M3 10.5l2.5-2.8c.38-.42.92-.66 1.48-.66h13.6c.97 0 1.62.99 1.27 1.9l-.7 1.56H3z"
        fill="#FFC83D"
      />
      <path
        d="M3 10.5l2.5-2.8c.38-.42.92-.66 1.48-.66h13.6c.2 0 .38.04.54.11L7.5 10.5H3z"
        fill="#FFD86B"
      />
    </svg>
  );
}
