import fitz

def is_close_to_color(color, target_color, threshold=0.1):
    distance = ((color[0] - target_color[0]) ** 2 +
                (color[1] - target_color[1]) ** 2 +
                (color[2] - target_color[2]) ** 2) ** 0.5
    return distance < threshold

def is_magenta(color):
    r, g, b = color
    return r > 0.5 and b > 0.5 and g < 0.3



def dropbox_qa(pdf):
    target_color = (0.9260547757148743, 0.0, 0.548302412033081)
    document = fitz.open(pdf)
    for page_num in range(len(document)):
        page = document.load_page(page_num)
        text_instances = page.get_drawings()
        my_list = []
        count = 1
        for text in text_instances:
            if text['items']:
                if text['color']:
                    if is_close_to_color(text['color'], target_color) == True:
                        if is_magenta(text['color']) == True:
                            count+=1
        return f'{count} instances of magenta lines with vector paths'
