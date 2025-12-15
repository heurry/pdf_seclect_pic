import os
from collections.abc import Generator
from typing import Any

import fitz
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.file.file import File


class PdfSeclectPicTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        pdf_input = tool_parameters.get("pdf_file") or tool_parameters.get("pdf_path")
        pdf_path_raw: str | None = None
        pdf_bytes: bytes | None = None
        pdf_display: str | None = None

        if isinstance(pdf_input, File):
            pdf_bytes = pdf_input.blob
            pdf_display = pdf_input.filename or pdf_input.url
        elif isinstance(pdf_input, dict):
            # Try to parse as File schema first
            try:
                file_obj = File.model_validate(pdf_input)
                pdf_bytes = file_obj.blob
                pdf_display = file_obj.filename or file_obj.url
            except Exception:
                pdf_path_raw = str(pdf_input.get("path") or pdf_input.get("url") or "").strip()
        elif isinstance(pdf_input, str):
            pdf_path_raw = pdf_input.strip()

        if pdf_bytes is None and not pdf_path_raw:
            raise ValueError("Parameter `pdf_file` is required and must be a PDF upload.")

        try:
            min_width = int(tool_parameters.get("min_width", 240))
            min_height = int(tool_parameters.get("min_height", 70))
        except (TypeError, ValueError) as exc:
            raise ValueError("`min_width` and `min_height` must be integers.") from exc

        if min_width <= 0 or min_height <= 0:
            raise ValueError("`min_width` and `min_height` must be positive.")

        doc = None

        if pdf_bytes is None:
            if not pdf_path_raw or not os.path.isfile(pdf_path_raw):
                raise FileNotFoundError(f"PDF file not found: {pdf_path_raw}")
            try:
                doc = fitz.open(pdf_path_raw)
                pdf_display = pdf_path_raw
            except Exception as exc:  # pragma: no cover - surface error to user
                raise RuntimeError(f"Failed to open PDF: {exc}") from exc
        else:
            try:
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            except Exception as exc:  # pragma: no cover - surface error to user
                raise RuntimeError(f"Failed to open PDF: {exc}") from exc

        pages_with_images: list[int] = []
        page_image_flags: list[int] = []
        total_pages = 0

        try:
            total_pages = doc.page_count
            for page_index in range(total_pages):
                page = doc[page_index]
                try:
                    image_list = page.get_images()
                except Exception:
                    page_image_flags.append(0)
                    continue

                has_image = False
                for img in image_list:
                    xref = img[0]
                    try:
                        base_image = doc.extract_image(xref)
                    except Exception:
                        continue

                    image_width = base_image.get("width")
                    image_height = base_image.get("height")
                    if image_width is None or image_height is None:
                        continue

                    if image_width * image_height >= min_width * min_height:
                        has_image = True
                        break
                if has_image:
                    pages_with_images.append(page_index + 1)
                    page_image_flags.append(1)
                else:
                    page_image_flags.append(0)
        finally:
            doc.close()

        pages_with_no_images = [index + 1 for index, flag in enumerate(page_image_flags) if flag == 0]

        yield self.create_json_message(
            {
                "pages_with_images": pages_with_images,
                "pages_with_no_images": pages_with_no_images,
                "matched_pages_count": len(pages_with_images),
                "total_pages": total_pages,
                "min_width": min_width,
                "min_height": min_height,
                "page_image_flags": page_image_flags,
                "source": pdf_display,
            }
        )

# 返回array[number]
# import json
# from typing import Any, Dict, List

# def main(arg1: Any) -> Dict[str, List[int]]:
#     def to_int(x: Any) -> int:
#         if isinstance(x, (int, float, bool)):
#             return int(x)
#         if isinstance(x, str):
#             return int(float(x.strip()))
#         raise ValueError(f"Non-numeric item: {x!r}")

#     data = json.loads(arg1) if isinstance(arg1, str) else arg1

#     if isinstance(data, list):
#         if not data:
#             raise ValueError("arg1 list is empty")
#         # If list wraps a single dict with flags, unwrap it
#         if len(data) == 1 and isinstance(data[0], dict) and "page_image_flags" in data[0]:
#             data = data[0]
#         else:
#             return {"result": [to_int(x) for x in data]}

#     if isinstance(data, dict) and "page_image_flags" in data:
#         raw = data["page_image_flags"]
#     else:
#         raw = data

#     if not isinstance(raw, (list, tuple)):
#         raise ValueError("page_image_flags must be a list")

#     return {"result": [to_int(x) for x in raw]}
