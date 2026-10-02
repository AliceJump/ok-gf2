import cv2
from rapidocr import RapidOCR, VisRes

vis = VisRes()

engine = RapidOCR(
    params={
        "Global.use_cls": False,
        "Global.max_side_len": 4000,
        "Global.min_side_len": 0,
        "EngineConfig.onnxruntime.use_dml": True,
    }
)
image_path = "tests/images/negative_text.png"
img = cv2.imread(image_path)
# img = cv2.resize(img, (1920, 1080))
for i in range(1):
    result = engine(img, use_cls=False)
    print(result.elapse)

for i in range(len(result.boxes)):
    pos = result.boxes[i]
    text = result.txts[i]
    width, height = round(pos[2][0] - pos[0][0]), round(pos[2][1] - pos[0][1])

    print(f"text: {text} width: {width}, height: {height}")

font_path = "tests/font/FZYTK.TTF"

vis_img = vis(image_path, result.boxes, result.txts, result.scores, font_path=font_path)
cv2.imwrite("vis_single.png", vis_img)
