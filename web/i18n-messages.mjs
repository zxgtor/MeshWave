export default `
局部保护顶点数　	Locally protected vertices　
编辑状态已变化，旧检测建议已清除。	Edits changed; previous detection suggestions were cleared.
请求失败	Request failed
请先恢复原始模板，再修改排除区域。	Restore the original template before editing exclusions.
区域包含对应点或曲线节点，请缩小范围或先调整节点。	This region contains correspondence or curve points. Reduce the area or move the points first.
不能排除全部目标面。	Cannot exclude all target faces.
该区域无需更改。	No change needed in this region.
排除	Exclude
恢复	Restore
已	Updated:
个三角面。	triangles.
完成几何贴合并加载两侧贴图后，可进行纹理细化。	Fit the geometry and load both textures before texture refinement.
纹理预览	Texture Preview
纹理细化	Texture Refinement
手动修正	Manual Corrections
检测到	Detected
对建议点，视图中以 A 编号显示。采用前请检查；原点对尚未替换。	suggested pairs, marked A in the views. Review before accepting; existing pairs are unchanged.
已跳过：	Skipped:
所有候选均已映射。检测建议可能有误，请检查眼角、鼻翼和嘴角。	All candidates were mapped. Suggestions may be incorrect; inspect eye corners, nose wings, and mouth corners.
对	pairs
模型缺少完整 UV	Mesh has incomplete UVs
有效 UV 像素覆盖率	Valid UV pixel coverage
像素未匹配 ·	unmatched pixels ·
个零面积 UV 面	zero-area UV faces
已恢复贴图 ·	Restored texture ·
未建立工程	No Project
有未保存更改	Unsaved Changes
已保存	Saved
面 · 目标	faces · Target
面	faces
正在笔刷修正	Editing with Brush
正在处理	Processing
纹理细化结果	Texture-refined Result
手动修正结果	Manually Edited Result
贴合完成	Fitting Complete
重选对应点	Reselect Correspondence
编辑排除区域	Edit Exclusions
正在处理，请稍候…	Processing, please wait…
左侧显示结果，可叠加目标检查，或导出 OBJ	Result shown on the left. Overlay the target to inspect, or export OBJ
下一步：Shift + 点击右侧目标的相同部位	Next: Shift-click the same location on the right target
Shift + 点击左侧模板，开始选择下一对对应点	Shift-click the left template to start the next pair
左侧模板	left template
右侧目标	right target
Shift + 点击	Shift-click
，替换第	to replace pair
对中的点	point
Shift + 点击两侧表面添加曲线节点；两侧起点与绘制方向需对应，生成预览后采用	Shift-click both surfaces to add curve points. Match starting points and direction, then preview and accept
Shift + 点击任一模型	Shift-click either mesh to
区域，红色为已排除面	regions; excluded faces are red
在左侧按住左键修正；Alt + 左键旋转，右键平移；Ctrl+Z 撤销，Ctrl+Y 重做	Left-drag on the left mesh to edit; Alt + left-drag to rotate, right-drag to pan; Ctrl+Z undo, Ctrl+Y redo
重选第	Reselect pair
点	point
删	Delete
删除第	Delete pair
已删除第	Deleted pair
对。	pairs.
模板 #	Template #
→ 等待目标	→ Select target
批处理进行中	Batch Running
使用固定模板与参数依次求解；当前工作区保留，进度见批处理列表。	Solving sequentially with a fixed template and settings. Your workspace is retained; see the batch list for progress.
请先恢复原始模板，再修改对应点。	Restore the original template before editing correspondences.
请先导入两个模型。	Import both meshes first.
此点在排除区域内，请先恢复该区域。	This point is excluded. Restore the region first.
请在正在重选的一侧点击。	Click on the side being reselected.
此顶点已被其他点对使用。	This vertex is already used by another pair.
此点已被其他点对使用。	This point is already used by another pair.
此模板点已被选用。	This template point is already selected.
此目标点已被选用。	This target point is already selected.
已更新对应点。	Correspondence updated.
此模板顶点已被选用。	This template vertex is already selected.
已选模板点 #	Selected template vertex #
已选模板点	Selected template point
，请在右侧选择对应点。	; select its match on the right.
请先在左侧选择模板点。	Select a template point on the left first.
此目标顶点已被选用。	This target vertex is already selected.
最多支持 100 对对应点。	Up to 100 correspondence pairs are supported.
已添加第	Added pair
对对应点。	correspondence pairs.
请 Shift + 点击	Shift-click
的新位置；只修改所选点对的一侧。	at its new location; only this side of the selected pair changes.
正在从正面灰模渲染检测并映射表面点…	Detecting and mapping surface points from frontal untextured renders…
正在自动检测人脸对应点…	Detecting face correspondences…
已生成	Generated
对建议点，请检查 A 编号后点击“采用建议”。	suggested pairs. Check A markers, then click Accept Suggestions.
检测未完成；原点对保留。	Detection did not complete; original pairs are retained.
已采用	Accepted
对自动点，可在下方列表逐点重选或删除。	automatic pairs. Reselect or delete them in the list below.
已采用自动对应点，请检查后开始贴合。	Automatic correspondences accepted. Review them before fitting.
已取消检测建议，原点对未改变。	Suggestions discarded; original pairs are unchanged.
起	Start
请先完成点对编辑或检测预览，并恢复原始模板后再绘制曲线。	Finish point editing or detection preview and restore the original template before drawing curves.
曲线路径已更新。两侧按相同方向绘制后，生成对应点预览。	Curve paths updated. Draw both sides in matching directions, then preview correspondences.
请先点击“新增成对曲线”。	Click Add Curve Pair first.
曲线	Curve
预览	Preview
对新采样点（S 编号）。采用后替换此前未手动修改的曲线点，保留普通点对；两侧“起”节点必须对应。	new sample pairs (S markers). Accepting replaces unedited curve-generated pairs and retains ordinary pairs. Match the Start points on both sides.
曲线点已生成，请检查采样方向与位置。	Curve points generated. Check sampling direction and positions.
对曲线点，共	curve pairs; total
对。曲线点可在普通列表中编辑，编辑后按普通点处理。	pairs. Curve points can be edited in the normal list; edited points become ordinary pairs.
曲线对应点已采用，可开始贴合。	Curve correspondences accepted. Ready to fit.
已取消预览，现有点对未改变。	Preview cancelled; existing pairs are unchanged.
单文件上限为 18 MB。	File size limit is 18 MB.
模板上限为 100,000 顶点，请先简化模型。	Templates are limited to 100,000 vertices. Simplify the mesh first.
UV 就绪	UVs Ready
无完整 UV	Incomplete UVs
顶点 ·	vertices ·
三角面 ·	triangles ·
正在读取	Reading
模型已载入。	Mesh loaded.
已撤销。	Undone.
已清空对应点。	Correspondences cleared.
已恢复原始模板，保留对应点与排除区域。	Original template restored; correspondences and exclusions retained.
已取消重选，原点对未改变。	Reselection cancelled; original pairs are unchanged.
撤销会排除现有对应点或曲线节点，请先调整节点。	Undo would exclude existing correspondence or curve points. Move them first.
撤销会排除全部目标面，无法执行。	Cannot undo: it would exclude all target faces.
已撤销上一次区域操作。	Last region edit undone.
已清空两侧排除区域。	Exclusions cleared on both sides.
正在从粗到细求解，较大模型可能需要数分钟…	Solving coarse to fine. Large meshes may take several minutes…
正在单阶段求解，较大模型可能需要数分钟…	Running single-stage fitting. Large meshes may take several minutes…
平均三角面距离	Mean Surface Distance
对应点最大误差	Max Correspondence Error
法线过滤	Normal Filter
个最近匹配 · 防翻面限步	nearest matches · Flip-prevention steps
次	steps
次迭代 · 顶点数与拓扑保留	iterations · Vertex count and topology preserved
防翻面保护已提前停止迭代，保留最后安全结果；请检查对应点和局部形变。	Flip prevention stopped iterations early and retained the last safe result. Inspect correspondences and local deformation.
贴合完成。请旋转视图、叠加目标检查结果。	Fitting complete. Rotate the views or overlay the target to inspect.
多阶段	Multi-stage
单阶段	Single-stage
· 总耗时	· Total time
秒 · 匹配查询	s · Correspondence queries
点次	point queries
阶段	Stage
控制点	Control Points
匹配点	Matches
完整网格误差	Full Mesh Error
耗时	Time
（保护限步）	(protection limited the step)
秒	s
已导出 OBJ，保留原始面和 UV。	OBJ exported with original faces and UVs.
笔刷半径为 0.2%–20%，强度为 1–100。	Brush radius must be 0.2%–20% and strength 1–100.
几何已手动修改，先前纹理细化统计已失效。	Geometry was edited manually; previous texture refinement statistics are no longer valid.
几何已手动修正，原求解误差与阶段统计已失效。	Geometry was edited manually; original fitting errors and stage statistics are no longer valid.
本笔已修改	This stroke changed
个顶点权重；几何保持不变。	vertex weights; geometry is unchanged.
防翻面保护阻止了该步，请减小强度。	Flip prevention blocked this step. Reduce strength.
未找到距离及法线合格的目标表面，可增大半径或检查法线方向。	No target surface satisfies distance and normal limits. Increase radius or check face orientations.
范围内没有变化：可能已贴面，或没有可移动顶点。	No change in this area: already on the surface, or no movable vertices.
· 防翻面已限步	· Step limited by flip prevention
个顶点无合格投射	vertices without valid projection
个顶点	vertices
已取消当前权重笔画。	Weight stroke cancelled.
已绘制	Painted
个顶点权重；可撤销	vertex weights; undo available:
笔。	strokes.
本笔未改变权重。	This stroke did not change weights.
已取消当前笔画，恢复笔画前状态。	Stroke cancelled; previous state restored.
已完成一笔，修改	Stroke complete; changed
个顶点；可撤销	vertices; undo available:
本笔未改变几何：未找到距离及法线合格的目标表面。	No geometry changed: no target surface satisfies distance and normal limits.
本笔未改变几何。	This stroke did not change geometry.
已取消当前笔画。	Stroke cancelled.
权重绘制完成，几何和烘焙贴图保持不变。	Weight painting complete; geometry and baked texture are unchanged.
笔刷操作完成；几何变化后请重新烘焙贴图。	Brush edit complete. Rebake after geometry changes.
正在准备笔刷约束…	Preparing brush constraints…
笔刷就绪：在左侧按住左键修正。	Brush ready: left-drag on the left mesh to edit.
笔刷就绪。	Brush ready.
投射笔刷就绪，投射距离上限为当前笔刷半径。	Projection brush ready. Maximum projection distance is the current brush radius.
已设置	Set
个顶点权重为	vertex weights to
%；硬锁定不变。	%; hard constraints are unchanged.
可撤销	Undo available:
笔 · 可重做	strokes · Redo available:
笔	strokes
已恢复权重，几何和烘焙贴图保持不变。	Weights restored; geometry and baked texture are unchanged.
已撤销一笔，贴图仍需重新烘焙。	Stroke undone. The texture still needs rebaking.
已重做一笔。	Stroke redone.
输入贴图已变化，先前纹理统计失效；细化几何保留。	Input texture changed; previous texture statistics are invalid. Refined geometry is retained.
正在读取贴图…	Reading texture…
模型需要完整 UV 才能显示贴图。	The mesh needs complete UVs to display a texture.
输入贴图上限为 8 MB。	Input texture size limit is 8 MB.
无法读取图片。	Cannot read the image.
贴图已载入；之前的烘焙结果已清除，模型贴合结果保留。	Texture loaded. Previous bake cleared; fitted geometry retained.
已移除贴图并清除旧烘焙结果。	Texture removed and previous bake cleared.
正在烘焙纹理，高分辨率可能需要数分钟…	Baking texture. High resolutions may take several minutes…
纹理烘焙完成，覆盖率	Texture baked. Coverage
%；未匹配区域为透明。	%; unmatched regions are transparent.
已导出模板 UV 贴图 PNG。	Template UV texture exported as PNG.
导出失败。	Export failed.
已导出 OBJ、MTL、颜色贴图和透明度贴图，解压后一起使用。	Exported OBJ, MTL, color, and opacity images. Extract and keep the files together.
工程超过 96 MB，无法保存。	Project exceeds 96 MB and cannot be saved.
工程已下载，包含模型、贴图、点对、排除区域、参数和当前结果。	Project downloaded with meshes, textures, pairs, exclusions, settings, and the current result.
打开工程将替换当前未保存的工作，是否继续？	Opening a project will replace your unsaved work. Continue?
正在检查工程文件…	Checking project file…
工程文件上限为 96 MB。	Project file size limit is 96 MB.
工程文件不是有效的 JSON。	Project file is not valid JSON.
曲线已恢复，路径需检查：	Curves restored; check paths:
已恢复纹理细化结果；重新计算可查看本次统计。	Texture-refined result restored. Recompute to view current statistics.
尚未进行纹理细化。	No texture refinement yet.
自定义	Custom
已恢复纹理细化结果；本次未重算纹理统计，可继续检查、烘焙或导出。	Texture-refined result restored without recomputing statistics. You can inspect, bake, or export it.
已恢复手动修正结果；原求解统计已失效，可继续修正或导出。	Manually edited result restored. Original solver statistics are invalid; continue editing or export.
已恢复保存的结果；尚未按当前质量约束重新验证，重新计算后显示误差和保护指标。	Saved result restored, without validation against current quality constraints. Recompute to see error and protection metrics.
已打开工程：	Opened project:
打开失败：	Open failed:
；当前工程未替换。	; current project was not replaced.
纹理细化参数超出允许范围。	Texture refinement settings are out of range.
纹理细化预览	Texture Refinement Preview
左侧显示候选几何；采用后才替换结果，取消保留原结果。此时保存工程仍保存原结果。	Candidate geometry is shown on the left. Accept to replace the result, or cancel to retain it. Saving now still saves the original result.
纹理灰度残差	Grayscale Texture Residual
个匹配顶点 ·	matched vertices ·
视图 ·	views ·
次迭代 ·	iterations ·
正在渲染纹理并计算双向光流…	Rendering textures and computing bidirectional optical flow…
预览：	Preview:
。请旋转检查后采用；原结果尚未替换。	. Rotate to inspect before accepting; the original result is unchanged.
纹理细化预览已生成。	Texture refinement preview generated.
已取消纹理细化预览，原结果和贴图保持不变。	Texture refinement preview cancelled; original result and texture are unchanged.
已取消纹理细化预览。	Texture refinement preview cancelled.
已采用纹理细化；原几何求解统计与烘焙贴图已失效。	Texture refinement accepted; original geometry statistics and baked texture are no longer valid.
。已采用，请重新烘焙贴图。	. Accepted; please rebake the texture.
已采用纹理细化，保留拓扑、UV、硬点和软权重。	Texture refinement accepted, preserving topology, UVs, hard points, and soft weights.
非流形边	Non-manifold Edges
非流形顶点	Non-manifold Vertices
无效/重复原始面	Invalid / Duplicate Original Faces
其中重复三角面	Duplicate Triangles (Subset)
无效顶点	Invalid Vertices
绕序冲突边	Winding-conflict Edges
无效 UV / 引用	Invalid UVs / References
修复预览	Repair Preview
原始诊断	Original Diagnostics
· 检测到问题	· Issues detected
· 所列问题为 0	· No listed issues
当前工程尚未替换。	Current project has not been replaced.
个有效三角面	valid triangles
原文件第	Original file line
行：	:
另有	Additional
条记录未列出。	records omitted.
查看修复后	View Repaired
诊断 ·	Diagnostics ·
正在检查网格…	Inspecting mesh…
，并重置模板软权重	, and reset template soft weights
应用修复将替换	Applying this repair will replace
，清空点对、曲线、排除区和贴合结果	, clearing correspondences, curves, exclusions, and fitted results
。可撤销一次；开始其他编辑后撤销失效。原文件不会被覆盖。	. One undo is available until another edit. The original file will not be overwritten.
诊断 OBJ 文件上限为 18 MB。	Diagnostic OBJ file size limit is 18 MB.
正在生成修复预览…	Generating repair preview…
修复后没有完整 UV，不保留该侧贴图。	Repaired mesh has incomplete UVs; its texture will not be retained.
无法生成修复结果：	Cannot generate repair:
已恢复修复前结果；重新计算可刷新误差统计。	Pre-repair result restored. Recompute to refresh error statistics.
已恢复纹理细化结果；统计未重算。	Texture-refined result restored; statistics were not recomputed.
网格已修复，请重新检测或选择对应点。	Mesh repaired. Detect or select correspondences again.
网格已修复，请重新建立曲线。	Mesh repaired. Recreate curves.
已应用修复；点对等约束已清空，可撤销上次修复。	Repair applied; correspondence constraints cleared. You can undo the last repair.
已恢复修复前曲线与点对。	Pre-repair curves and pairs restored.
已恢复修复前工程；笔刷撤销历史未恢复。	Pre-repair project restored; brush undo history was not restored.
载入演示会替换当前模型和对应点，是否继续？	Loading the demo will replace the current meshes and correspondences. Continue?
正在载入演示…	Loading demo…
演示已载入，包含 UV、扫描棋盘贴图和 7 对点；贴合后可烘焙纹理。	Demo loaded with UVs, a checkerboard scan texture, and 7 point pairs. Fit first, then bake textures.
批量光流需要模板完整 UV 和原始参考贴图。	Batch optical flow requires complete template UVs and an original reference texture.
三维视图初始化失败：	3D viewport initialization failed:
等待上传完成	Awaiting Upload Completion
顺序求解中	Solving Sequentially
等待当前项完成后停止	Stopping After Current Item
正在打包	Packaging
全部完成	Completed
完成，部分失败	Completed with Errors
已取消	Cancelled
服务中断	Service Interrupted
任务失败	Job Failed
达到输出上限	Output Limit Reached
待上传	Awaiting Upload
等待	Pending
待序列处理	Awaiting Sequence Processing
成功	Succeeded
跳过	Skipped
一次最多选择 100 张贴图。	Select up to 100 textures at once.
已选择	Selected
张贴图，按扫描主名匹配。	textures, matched by scan basename.
已导出	Exported
的点对与目标排除区。	: correspondences and target exclusions.
每批最多 50 个 OBJ，文件名不能重复。	Up to 50 OBJ files per batch; filenames must be unique.
每个约束 JSON 上限 1 MB。	Each constraints JSON is limited to 1 MB.
不是有效的批处理约束 JSON。	Not a valid batch constraints JSON.
约束文件来自不同模板，不能合并。	Constraints from different templates cannot be merged.
约束中存在无效或重复文件名。	Constraints contain invalid or duplicate filenames.
约束 JSON 合计需要 1–50 项。	Constraints JSON files must contain 1–50 items in total.
已加载	Loaded
项独立扫描约束。	per-scan constraints.
约束加载失败：	Constraints load failed:
；原约束保留。	; original constraints retained.
请先在第 06 节给模板加载原始参考贴图并确保完整 UV。	Load the original template reference texture in section 06 and ensure complete UVs first.
使用第 06 节模板原始参考贴图。	Uses the original template reference texture from section 06.
请先将左侧模型转到正面；共用第 08 节光流参数、当前左侧相机朝向和软权重。几何与光流独立求解；勾选时序后再跨帧平滑。	Face the left mesh forward. Reuses section 08 optical flow settings, left camera direction, and soft weights. Geometry and flow are solved independently; temporal smoothing follows if enabled.
每项使用其独立约束	per-scan constraints
复用当前已采用点对及排除区	reuse accepted pairs and exclusions
个扫描；	scans;
选择扫描并启动；结果自动打包为 ZIP。	Choose scans and start; results are packaged as ZIP.
正在固定模板与参数快照…	Capturing template and settings…
正在上传：	Uploading:
· 待序列处理	· Awaiting sequence processing
· 当前项计算中	· Current item processing
· 成功	· Succeeded
· 失败	· Failed
· 跳过	· Skipped
· 等待	· Pending
；上次结果仍可下载。	; previous results remain available for download.
新队列待启动 ·	New Queue Ready ·
项	items
结果目录：	Output folder:
异常修复中	Repairing Anomaly
异常检测中	Detecting Anomalies
时序平滑中	Temporal Smoothing
光流细化中	Optical Flow Refinement
正在烘焙	Baking
正在插值和受约束重新贴合	Interpolating and refitting with constraints
异常几何修复成功	Anomalous geometry repaired
修复失败，继续隔离	Repair failed; remains isolated
无可用修复区间	No usable repair interval
修复已取消	Repair cancelled
修复已中断	Repair interrupted
· 插值	· Interpolation
待异常检测	Awaiting anomaly detection
可疑异常 · 已隔离	Suspected Anomaly · Isolated
几何已修复 · 原扫描异常保留	Geometry Repaired · Original Scan Anomaly Retained
未发现异常信号	No anomaly signals detected
上下文不足 · 已检查可用信号	Limited Context · Available Signals Checked
异常检测失败	Anomaly detection failed
异常检测中断	Anomaly detection interrupted
未完成异常检测	Anomaly detection incomplete
· 扫描粗糙度	· Scan roughness
% · 离面误差	% · Surface error
光流残差	Optical Flow Residual
个匹配顶点	matched vertices
双向片段边界 · 保留本帧几何	Bidirectional Boundary · Frame Geometry Retained
时序历史起点 · 保留本帧几何	Temporal History Start · Frame Geometry Retained
· 后帧	· Next frame
时序平滑 ·	Temporal Smoothing ·
个顶点 · 最大修正	vertices · Max correction
· 前帧	· Previous frame
自适应强度	Adaptive Strength
%（均值） · 速度	% (mean) · Speed
%/帧（最大） · 快速保护	%/frame (max) · Fast-motion protection
顶点	vertices
已烘焙	Baked
² · 覆盖	² · Coverage
% · 未匹配	% · Unmatched
像素	pixels
独立约束 JSON 没有与所选文件名匹配的项目。	No per-scan constraints match the selected filenames.
单文件超过 18 MB 上限。	File exceeds the 18 MB limit.
扫描匹配到多张同主名贴图，请只保留一张。	Multiple textures match this scan basename. Keep only one.
未找到同主名 PNG/JPEG 贴图。	No PNG/JPEG texture with a matching basename.
扫描贴图仅支持 PNG/JPEG，单张上限 8 MB。	Scan textures must be PNG/JPEG, up to 8 MB each.
无法读取扫描贴图。	Cannot read scan texture.
上传尚未完成。请取消该草稿后重新选择扫描。	Upload incomplete. Cancel this draft and select scans again.
任务查询失败：	Job query failed:
取消已请求：当前求解项会先完成。	Cancellation requested. The current item will finish first.
下载失败。	Download failed.
ZIP 下载未完成：	ZIP download incomplete:
；可重试下载。	; you can retry the download.
笔刷权重必须与模板顶点一一对应，范围为 0–1。	Brush weights must match template vertices and be within 0–1.
模板包含零面积面，无法启用笔刷。	Template has zero-area faces; brushes cannot be enabled.
当前结果不满足防翻面约束，请重新贴合。	Current result violates flip-prevention constraints. Refit it.
权重绘制参数无效。	Invalid weight painting settings.
笔刷参数无效。	Invalid brush settings.
投射目标或法线夹角无效。	Invalid projection target or normal angle.
目标保留区域没有有效三角面，无法投射。	No valid triangles in the retained target region for projection.
`.trim().split('\n').map(line=>line.split('\t'));
