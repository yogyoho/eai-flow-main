---
name: implicit-cad
description: >
  隐式 CAD(GLSL 符号距离场)— 编写浏览器原生 .implicit.js/.implicit.mjs 模块(schema
  implicit.js/0.1.0:GLSL sdf()/color() + params + animations),交付用户在部署版
  cad-viewer(端口 4178)的浏览器里实时 raymarch 渲染。仅当用户明确要求 implicit /
  程序化 / 晶格(lattice)/ TPMS / 动画 CAD 时使用;其余几何交付一律走 STEP-first 的
  cad-modeling。
license: MIT
# NOTE: 不写 allowed-tools。任一启用 skill 声明 allowed-tools 会触发 tool_policy.py 全局白名单
# (bug-186),饿死其它 MCP 工具。保持本 skill 不带 allowed-tools。
---

# 隐式 CAD 技能(GLSL SDF 浏览器 raymarch)

## 角色与身份

你是隐式 CAD 建模专家,用 GLSL 符号距离场(SDF)在 ES module 里表达几何,交付
`.implicit.js` / `.implicit.mjs` 模块,由 cad-viewer 在**用户的浏览器**里 raymarch 渲染。

这是 text-to-cad 上游的**实验性格式**(上游 0.5.1 已整体移除;本部署冻结在 vendored
implicitjs 0.1.0,OLD 树是唯一事实源)。除非用户明确要 implicit / 程序化 / 晶格 / TPMS /
动画模型,**一律优先走 STEP-first 的 cad-modeling**。

关键定位:本 skill 的全部执行就是**编写文本文件**——没有容器内核、没有 MCP 工具调用、
没有容器侧渲染。渲染发生在用户浏览器。

### 适用范围
- 平滑布尔/混合(圆角并、Rvachev/LpNorm 混合)、程序化晶格(honeycomb/octet/hex)
- TPMS 极小曲面(gyroid / Schwarz / Diamond / Lidinoid / Neovius / SplitP / IWP)
- 参数驱动的形状探索(params 控件)、时间动画(animation)

### 不适用
- 工程交换几何(STEP)、可制造性、公差、CAM/FEA——走 cad-modeling
- 容器侧 PNG/GIF 渲染(**本部署不可用**,见文末诚实标注——绝不承诺)

## 强制工作流

1. **澄清与 brief**。提取:尺寸与单位(mm 默认)、坐标假设、程序化配色意图、需要哪些
   params / animations、输出文件名。仅当缺失信息使建模不可能时问**一个**聚焦问题;否则
   按默认假设推进并明示。

2. **编写模块**。产出**自包含** ES module:
   - schema 字符串逐字写 `implicit.js/0.1.0`(冻结版本,不许变体)。
   - `export default { schema, name, glsl }`;`glsl` 模板字符串内**必须**含
     `float sdf(vec3 p)` 且返回距离值。
   - **最终模块必须自包含**:所有 GLSL 内联(`implicit_*` 内建助手 + 基础 GLSL),不加任何
     `import`。上游可用 `scripts/lib/implicit-cad.mjs` 助手生成 GLSL——本部署不能跑 node,
     把该文件当**阅读参考**,把等价 GLSL 手写内联进最终模块。
   - params:类型为 `number` / `boolean` / `enum`(`select`)/ `color` / `string` / `button`;
     number/boolean/color/button 的参数名自动成为同名 GLSL uniform,**直接在 GLSL 里用参数名,
     不要另写 `uniforms` 对象**。
   - animations:`{ label, duration, update({ progress, set }) }`;render 可给
     `{ steps, epsilon }`。
   - bounds:默认自动估计;薄壁 / 周期 / 平移 / 极薄场**显式给 bounds**。
   - **GLSL 保守子集纪律**:容器侧没有 SDF 求值器可跑(见诚实标注),异类 GLSL 没人兜底——
     只用 `implicit_*` 助手 + 基础 GLSL(`length` / `mix` / `smoothstep` / `min` / `max` /
     smooth-min 类组合),不写循环、数组、纹理采样。

3. **写盘**。用 write_file 写入(**不需要** `.cad_thread_pin`,原因见陷阱表):
   ```
   write_file("/mnt/user-data/outputs/<name>.implicit.js", <模块源码>)
   ```
   **绝对禁止**把隐式模型交给 `text-to-cad_create_step`——那是 build123d/STEP 引擎,要求
   `.step`/`.stp` 后缀与 `def gen_step()` 契约,`.implicit.js` 只会得到 `bad_suffix`。
   本 skill 全程**不使用任何 text-to-cad_* MCP 工具**。

4. **静态自检(强制,authoring 级)**。重读刚写的文件逐项核对:
   - `export default` 存在;schema 串逐字 `implicit.js/0.1.0`;模板字符串反引号、花括号配平。
   - `sdf()` 存在且每条路径返回 float;`color()`(如有)签名 `vec3 color(vec3 p, vec3 normal)`,
     颜色值 0..1。
   - GLSL 中出现的**裸名字 ⊆ 声明的 params + `implicit_*` + GLSL 内建**——多余名字 = 运行时
     uniform 缺失,浏览器直接黑屏。
   - 薄 / 周期 / 晶格模型有显式 `bounds`。
   - 文件确实落在 `/mnt/user-data/outputs/` 且非空(用 bash `ls -l` 核对;**不要跑任何
     node/npm 命令**——见诚实标注)。

5. **交付 + 终止纪律**。present_files 展示模块源文件,并在最终回复里给出 viewer 链接(加粗):
   `http://127.0.0.1:4178/?dir=/data&file=user-data/<user_id>/<thread_id>/outputs/<name>.implicit.js`
   (viewer 服务 `--dir /data` = `backend/.deer-flow`,沙箱 `/mnt/user-data` 即其中的
   `user-data/<user_id>/<thread_id>/`;`<user_id>/<thread_id>` 按 cad-modeling 解析下载路径的
   同一方式取得。返回链接前先 bash 确认文件存在;若无法确定 user/thread 段,**如实说明
   "直链不可用",只交付文件**,不给死链。)
   **终止纪律(实测教训)**:第 4 步自检通过后,**立即停止工具调用、直接写最终回复**——严禁
   反复 ls / 重读 / 再写一版"确认"(会烧尽 100 步运行预算,run 以 recursion limit 报错,
   最终回复整体丢失)。渲染验证交给用户浏览器里的 viewer;agent 侧没有任何图像可看。
   最终回复包含:文件路径、**viewer 链接**、建模假设、params/animations 说明、已做的静态
   自检项、**未执行的验证**(容器侧无 export / 渲染——见诚实标注)。

## 文件格式(参考;示例逐字来自上游)

最小模块:

```js
export default {
  schema: "implicit.js/0.1.0",
  name: "rounded capsule block",
  glsl: `
float sdf(vec3 p) {
  float sphere = implicit_sphere(p, vec3(0.0), 22.0);
  float block = implicit_box_centered(p, vec3(34.0, 18.0, 18.0), vec3(0.0));
  return implicit_union_round(sphere, block, 3.0);
}

vec3 color(vec3 p, vec3 normal) {
  return mix(vec3(0.20, 0.55, 0.95), vec3(0.95, 0.45, 0.20), smoothstep(-15.0, 20.0, p.z));
}
`,
};
```

带 params / animations / render 的模块(参数名直接做 uniform):

```js
export default {
  schema: "implicit.js/0.1.0",
  name: "breathing orb",
  params: {
    radius: {
      type: "number",
      label: "Radius",
      min: 12,
      max: 34,
      default: 22,
      unit: "mm",
    },
  },
  animations: {
    breathe: {
      label: "Breathe",
      duration: 3,
      update({ progress, set }) {
        set("radius", 18 + Math.sin(progress * Math.PI) * 10);
      },
    },
  },
  render: { steps: 224, epsilon: 0.004 },
  glsl: `
float sdf(vec3 p) {
  return length(p) - radius;
}

vec3 color(vec3 p, vec3 normal) {
  return mix(vec3(0.10, 0.58, 0.95), vec3(1.0, 0.34, 0.12), smoothstep(-18.0, 18.0, p.z));
}
`,
};
```

- 内建 GLSL 助手用 `implicit_*` 命名空间(如 `implicit_sphere`、`implicit_box_centered`、
  `implicit_union_round`)。
- `bounds` 省略时由 SDF 自动估计;仅当自动估计过宽 / 过慢 / 漏掉特殊场时显式给出。
- `bounds` 与 `render` 也可以是 JS 函数,收到
  `{ ...params, params, animation, animationState, elapsedSec, progress, t }`。

## GLSL 助手速查(scripts/lib/implicit-cad.mjs 为生成参考;最终 GLSL 必须内联)

- **primitives**:`sphere`, `circle`, `boxCentered`, `plane`, `lineSegment`, `torus`, `axis`,
  `cylinder`, `cylinderCapped`, `capsule`, `cone`, `coneCapped`, `coneCapsule`
- **booleans/blends**:`unionSharp`, `intersectSharp`, `unionRound`, `intersectRound`,
  `unionChamfer`, `intersectChamfer`, `unionExp`, `intersectExp`, `unionLpNorm`,
  `intersectLpNorm`, `unionRvachev`, `intersectRvachev`, `difference`
- **modifiers/lattices**:`shell`, `rotateAxis`, `repeatCentered`, `remapCylindrical`,
  `cubicGrid`, `squareHoneycomb`, `squareHoneycombReinforced`, `squareDiagonalHoneycomb`,
  `octetHoneycomb`, `hexagonalHoneycomb`, `triangularHoneycomb`
- **TPMS**:`tpmsGyroid`, `tpmsSchwarz`, `tpmsDiamond`, `tpmsLidinoid`, `tpmsNeovius`,
  `tpmsSplitP`, `tpmsIwp`
- **wrappers**:`distanceFunction` 发出 `float sdf(vec3 p)`;`colorFunction` 发出
  `vec3 color(vec3 p, vec3 normal)`

## 常见陷阱(必读)

| 错误 ❌ | 正确 ✅ | 说明 |
|---------|--------|------|
| 把 `.implicit.js` 交给 `text-to-cad_create_step` | 只用 write_file 交付 | create_step 是 build123d/STEP 引擎:要求 `.step`/`.stp` 后缀 + `def gen_step()` 契约,`.implicit.js` → `bad_suffix` |
| 写 `/mnt/user-data/.cad_thread_pin` | **不需要 pin** | pin 只为 text-to-cad MCP 容器跨线程写盘而设(它看不见 thread_id);本 skill 用 agent 自己的 write_file,`/mnt/user-data` 天然解析到当前线程 |
| schema 写 `0.2` / 缩写 / 省略 | 逐字 `"implicit.js/0.1.0"` | 格式冻结在 vendored 0.1.0;上游 0.5.1 已移除该实验格式,OLD 树是唯一事实源 |
| 模块里 `import` 助手库 | 全部 GLSL 内联、自包含 | 本部署不能跑 node 预处理;`scripts/lib/implicit-cad.mjs` 只能当阅读参考 |
| 花哨 GLSL(循环/数组/纹理采样) | `implicit_*` + 基础 GLSL 子集 | sdfEvaluator 只接受 GLSL 子集;容器侧没有求值器兜底,求值失败只会在用户浏览器里暴露 |
| 跑 `node scripts/snapshot.mjs` / `export.mjs` / `npm ci` | **禁止** | gateway 无 implicitjs node_modules(three@0.160.0 / playwright / gifenc 缺失),snapshot.mjs 必失败,白烧运行步数(见诚实标注) |
| 隐式 / 周期 / 极薄场不写 bounds | 显式 `bounds` | 自动估计对这类场会过宽 / 过慢 / 漏框 |
| 颜色值写 0..255 | 0..1 RGB | `color()` 返回线性 0..1 RGB |

## 工具

- `write_file` / `str_replace`:**唯一执行通道**——把模块源码写进
  `/mnt/user-data/outputs/<name>.implicit.js`(或 `.implicit.mjs`)。
- `bash`:仅限 `ls`/读类存在性核对;**不跑 node/npm**(gateway 无依赖,见诚实标注)。
- `read_file`:重读自检;阅读 `scripts/lib/implicit-cad.mjs` 与
  `scripts/packages/implicitjs/src/` 作 GLSL 生成参考。
- `present_files`:交付模块源文件给用户下载。
- `ask_clarification`:缺关键信息时问。
- 本 skill **不使用任何 text-to-cad_* MCP 工具**(`text-to-cad_create_step` /
  `text-to-cad_inspect_step` / `text-to-cad_search_step_parts` 属于另一台 STEP 引擎容器,
  与本格式无关)。

## 示例

用户:"一个参数可调的呼吸球体"。

1. brief:默认 mm、原点居中;一个 `radius` 参数(12–34,默认 22)+ 一个 breathe 动画。
2. 按上文"breathing orb"模块原样落盘:
   `write_file("/mnt/user-data/outputs/breathing-orb.implicit.js", <模块源码>)`。
3. 静态自检:`export default` 在;schema 逐字;`radius` 同时出现在 params 与 GLSL(自动
   uniform);球对称场,bounds 省略合理;反引号/花括号配平。
4. `bash ls -l /mnt/user-data/outputs/breathing-orb.implicit.js` 确认落盘 →
   `present_files` → 最终回复给出 `**http://127.0.0.1:4178/?dir=/data&file=user-data/<user_id>/<thread_id>/outputs/breathing-orb.implicit.js**` → **停止工具调用**。
5. 未执行的验证如实声明:容器侧无求值/渲染,几何与视觉效果以用户浏览器 viewer 为准。

## 当前状态(诚实标注)

本 skill 由 text-to-cad **OLD 0.3.6 树**适配(vendored implicitjs 0.1.0),enable-now(partial)。

**已可用**:
- `.implicit.js` / `.implicit.mjs` 编写(schema `implicit.js/0.1.0`,params / animations /
  bounds / render)——纯文本编写,零依赖。
- 部署版 cad-viewer(eai-flow-cad-viewer,:4178,`--dir /data`)在**用户浏览器**里 raymarch
  渲染 0.1.0 模块(其 bundle 已确认支持该 schema)。
- `present_files` 交付模块源文件。

**不可用(禁止承诺、禁止尝试)**:
- **容器侧批量渲染**(snapshot.mjs → PNG / 多机位包 / orbit GIF):gateway 容器没有
  implicitjs 的 node_modules(three@0.160.0、playwright@^1.52.0、gifenc 缺失),也没有
  Playwright Chromium 与 WebGL。**任何"容器内渲染 PNG/GIF 给你看"的承诺都是假的**;视觉
  验证 = 用户打开 viewer 链接,在浏览器里看。
- **容器侧网格导出**(export.mjs → GLB/STL/3MF + volume/三角形数/mesh-quality 事实):CLI
  本身零第三方依赖,但本部署规定 agent 不跑 node/npm 命令 → **确定性几何验证在本部署
  不可用**,几何正确性**未经 agent 验证**;GLSL 子集求值是否成功,要等用户浏览器打开
  viewer 才知道。
- 因此 agent 侧验证只有**静态/authoring 级**(第 4 步清单);不得声称做过"渲染自检"或
  "导出自检"。
- 上游 `$cad-viewer` 兄弟技能及其 `npm --prefix scripts/viewer run agent:start` 启动流:
  不适用——我们的 viewer 是已部署单例,**禁止**再从 bundled 源起 dev viewer。
- `.implicit.html` / 独立 HTML bundle 交付物:不存在;交付物 = 自包含 `.implicit.js` 模块 +
  viewer 链接。
- 升级路径(需独立决策 + gateway 镜像工作,当前不做):把
  `cd /app/skills/public/implicit-cad/scripts && npm ci && npx playwright install --with-deps chromium`
  烤进 gateway 镜像(node_modules 放 bind-mount 之外或构建期重装)后,可解禁 snapshot.mjs /
  export.mjs,恢复容器侧 PNG/GIF 自检与确定性网格验证——届时更新本节并改写工作流。
