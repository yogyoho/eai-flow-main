---
name: cad-dxf
description: >
  用 ezdxf gen_dxf() 源经 text-to-cad_create_dxf 容器工具生成 2D DXF
  (垫片/面板/样板/下料图/激光等离子水刀切割轮廓)。域特定的 2D 工程图(矿机
  布置/化院图签)走 cad_compose_drawing。执行在 text-to-cad 容器内,agent 沙箱
  不跑 ezdxf。
license: MIT
# 注意:不要添加 allowed-tools。任何 enabled skill 声明 allowed-tools 会触发
# tool_policy.py 全局白名单(bug-186),饿死所有其他 MCP 工具。

> 上游出处:earthtojake/text-to-cad v0.3.6 `skills/dxf`(MIT)。EAI 适配:执行从
> 沙箱侧 `python scripts/dxf` 改为容器侧 `text-to-cad_create_dxf` MCP 工具;
> ezdxf 实体级校验因沙箱无 ezdxf 改为诚实声明(见诚实标注)。
---

# 2D DXF 生成(cad-dxf)

## 用途

自然语言 → 2D DXF 图纸/轮廓。**契约:`gen_dxf()` 返回 ezdxf 文档**(不是 build123d
几何!Sketch/BuildSketch 在这里无效)。两种源形态:

- **独立制图**:源只定义 `gen_dxf()`,用 ezdxf 图元(`msp.add_lwpolyline` /
  `add_circle` / `add_arc`)直接绘制。用于纯 2D 产物——垫片、面板、样板、切割下料图。
- **CAD 投影**:先按 cad-modeling 走通 STEP,再写一个含 `gen_dxf()` 的源(几何参数
  与 gen_step 同源命名),把 3D 零件的平面轮廓**换算成 ezdxf 图元**输出。

**分工边界**:通用机械 DXF 用本 skill;**带图签/标注的工程图**(矿山布置、化工图)
用 `cad_compose_drawing`(cad 服务器,mine-design / chemplant-design skill)。

## 强制工作流

1. **brief**:轮廓尺寸、孔槽、图层、单位、输出路径、校验目标。信息不足时最多问**一个**
   聚焦问题,否则按默认假设推进并明示。

2. **参数化源码**(cad-modeling 同款纪律):
   - 命名尺寸参数;`import ezdxf` 由容器环境提供,**源码直接可用**。
   - 单位毫米并显式设置(`doc.units = ezdxf.units.MM`);模型空间 1:1。
   - 切割轮廓 = 闭合多段线/闭合直线圆弧环;开放轮廓仅用于雕刻或参考线。
   - 图层承载意图:切割与折弯线分层,折弯图层名含 "bend"。

3. **钉线程**(text-to-cad 容器跨线程共享看不见 thread_id;不钉 → 文件落错线程 → 下载 404,
   bug-324):
   ```
   write_file("/mnt/user-data/.cad_thread_pin", "1")
   ```
   write_file 被拒(Permission denied)则 bash 兜底:`echo 1 > /mnt/user-data/.cad_thread_pin`

4. **容器执行**(与 create_step 同契约:相对路径 + workspace CWD 由工具内部处理):
   ⚠️ **source 传源码字符串本身,不是文件路径**(传路径会被 bad_args 拒绝)。完整示例:
   ```
   text-to-cad_create_dxf(
     source="import ezdxf\n\ndef gen_dxf():\n    doc = ezdxf.new('R2010')\n    doc.units = ezdxf.units.MM\n    msp = doc.modelspace()\n    ...轮廓图元...\n    return doc",
     output_path="/mnt/user-data/outputs/<name>.dxf"   ⚠️ 必须 .dxf 结尾
   )
   ```
   不要先 write_file 再传路径——工具自己把 source 落盘为同基名 `<name>.py`(上游约定:
   DXF 输出与生成器同目录同名)。

5. **交付与终止纪律**。工具返回 `{status:"ok", dxf}` 后:`present_files` 递 DXF 文件;
   最终回复含文件路径、实际跑过的检查、关键假设、未执行的验证。**停止工具调用直接写
   回复**——反复确认会烧尽 100 步运行预算导致回复整体丢失(实测)。

## 校验(诚实边界)

引擎成功 = DXF 产出且可解析(ezdxf 在容器内)。**agent 沙箱没有 ezdxf**,上游的
实体级校验(逐类型/图层实体计数、闭合标志、图幅范围)当前无执行通道——**不要假装跑过**。
回复里如实写"实体级校验未执行";只报 `status:"ok"` 与文件路径。DXF 无法在浏览器
viewer 预览(cad-viewer 只吃 GLB),视觉核查 = 用户下载后用 CAD 软件打开。

## 默认假设(用户未指定时)

- 单位毫米;模型空间 1:1;切割轮廓闭合;折弯线独立图层;原点 = 轮廓左下角。

## 常见陷阱

| 错误 ❌ | 正确 ✅ | 说明 |
|---------|--------|------|
| `gen_dxf()` 里用 build123d(`Sketch`/`BuildSketch`) | 用 **ezdxf 图元**(`msp.add_lwpolyline` 等) | **gen_dxf 返回 ezdxf 文档**;build123d 2D 对象在此无效(`with Sketch()` 直接 TypeError) |
| DXF 请求走 `text-to-cad_create_step` | 用 `text-to-cad_create_dxf` | create_step **硬拒 .dxf 后缀**(bad_suffix);两工具后缀约定相反 |
| `create_dxf` 传 `.step` 输出路径 | `output_path` 必须 `.dxf` 结尾 | 工具拒绝非 .dxf 后缀 |
| `source` 传文件路径 | **传源码字符串本身**(完整内联) | 传路径被 bad_args 拒绝 |
| 沙箱里 `import ezdxf` 跑校验脚本 | 诚实声明校验未执行 | agent 沙箱无 ezdxf;执行只在容器内 |
| 忘记钉线程 | 每线程先写 `.cad_thread_pin` | `no_thread_pin` 硬失败;落错线程 → 下载 404(bug-324) |
| 工程图(图签/标注)用本 skill | 用 `cad_compose_drawing` | 本 skill 出纯几何 DXF,不带图签/标注体系 |

## 当前状态(诚实标注)

- **已集成**:`text-to-cad_create_dxf`(gen_dxf 契约,容器内 ezdxf 产出)。
- **未集成**:实体级确定性校验(沙箱无 ezdxf);DXF 视觉预览(cad-viewer 仅 GLB);
  `SOURCE.py=OUTPUT.dxf` 多目标形态(工具单目标);上游 `$cad-viewer` 交接(改为
  递文件路径 + 如实说明无预览)。
- 分工:带图签工程图 → `cad_compose_drawing`(cad :8003);本 skill = 通用机械 DXF。
