# Gallery 运行时契约

这份约定用于避免 Blender 模型、Three.js 导航与作品目录再次发生错位。

## 信息结构

- **3D 空间导航**只有三个真实存在于 Master V1 模型中的目的地：`Archive of Tides`、`Cliff Gallery`、`Sunken Palace`。
- **作品主题**仍是六类：色彩、重构、光影、材质、氛围、物件。它们属于页面下方 Catalog 的筛选维度，不再伪装成六个 Blender 房间。
- 新增真实空间时，先在 Blender 中增加导航标记，再由网页读取标记；不得在 HTML 中另写一套坐标。

## 单一数据来源

1. `static/assets/gallery/gallery-data.json` 保存作品身份、标题、主题、缩略图和原图。
2. `scripts/build_atlantis_gallery_master.py` 按作品 ID、主题与策展角色选择 13 幅 3D 作品：
   - Archive：Color、Composition、Lighting 各一幅 Highlight；
   - Cliff：Material、Mood、Object 各一幅 Highlight；
   - Palace：六个主题各一幅 Exhibition，加一幅焦点人像。
3. Blender 导出的每个可点击画面携带 `gallery_artwork_thumb`；网页用它回查 `gallery-data.json`，墙面纹理与弹窗共享同一个作品记录。
4. Blender 导出的导航位置携带 `gallery_nav_id`，另有对应的 `gallery_nav_target_for` 注视点。Three.js 只读取这两个标记来设置相机。

## 禁止恢复的旧逻辑

- 不再用全局文件名排序后的数组切片决定墙上放哪一幅画。
- 不再在网页中维护六组历史房间坐标。
- 不再按“第几幅画”把 Blender 纹理与 Catalog 数组强行对应。
- 主题筛选与空间跳转不能共用同一组按钮或同一个 ID。

## 发布前门禁

```bash
python3 -B scripts/audit_gallery_artwork_binding.py
/Users/eee/Desktop/works/tools/bin/hugo --minify --cleanDestinationDir --baseURL https://brocademaple.xyz/
```

审计必须同时满足：

- 13 个可点击 GLB 画面且缩略图路径唯一；
- 每个 GLB 内嵌纹理与 Catalog 对应文件逐字节一致；
- 六个主题全部出现，每类至少两幅；
- 三个空间均同时具有相机位置标记与注视点标记。

需要人工复核的三条直达链接：

- `?review=archive-of-tides`
- `?review=cliff-gallery`
- `?review=sunken-palace`

任意一幅画可用 `?review=artwork&artwork=0` 到 `?review=artwork&artwork=12` 定位；这是验收入口，不是作品身份。作品身份始终由 `gallery_artwork_thumb` 决定。
