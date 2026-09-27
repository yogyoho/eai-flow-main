import { defineConfig } from "vitepress";

// 部署于 nginx /ontostudio/docs/ 子路径（独立静态容器 ontostudio-docs:3011）
export default defineConfig({
  lang: "zh-CN",
  title: "OntoStudio 文档中心",
  description: "本体系统术语解释 · 业务本体设计 · 功能操作指南",
  base: "/ontostudio/docs/",
  ignoreDeadLinks: true, // 骨架期允许占位链接，内容丰满后移除
  themeConfig: {
    siteTitle: "OntoStudio 文档中心",
    nav: [
      { text: "首页", link: "/" },
      { text: "术语解释", link: "/glossary/" },
      { text: "业务本体设计", link: "/design/eia-model" },
      { text: "功能操作", link: "/guide/" },
      { text: "更新记录", link: "/changelog" },
    ],
    sidebar: {
      "/glossary/": [
        {
          text: "术语解释",
          items: [
            { text: "术语总览", link: "/glossary/" },
            { text: "eia 域（环评）", link: "/glossary/eia" },
            { text: "doc_graph 域（文档图谱）", link: "/glossary/doc-graph" },
          ],
        },
      ],
      "/design/": [
        {
          text: "业务本体设计",
          items: [
            { text: "eia 域模型", link: "/design/eia-model" },
            { text: "doc_graph 骨架", link: "/design/doc-graph" },
          ],
        },
      ],
      "/guide/": [
        {
          text: "功能操作",
          items: [{ text: "九大模块操作指南", link: "/guide/" }],
        },
      ],
      "/": [
        {
          text: "总览",
          items: [
            { text: "首页", link: "/" },
            { text: "更新记录", link: "/changelog" },
          ],
        },
      ],
    },
    search: {
      // 本地全文搜索——内网/离线环境可用，无外部服务依赖
      provider: "local",
      options: {
        translations: {
          button: { buttonText: "搜索文档", buttonAriaLabel: "搜索文档" },
          modal: {
            noResultsText: "未找到结果",
            resetButtonTitle: "清除查询",
            footer: { selectText: "选择", navigateText: "切换", closeText: "关闭" },
          },
        },
      },
    },
    outline: [2, 3],
  },
});
