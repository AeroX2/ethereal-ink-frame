from shlex import quote
from pathlib import Path
import subprocess
import os
import sys
import uuid
import random

from celery import shared_task, Celery
from celery.signals import worker_ready
from celery_singleton import Singleton
from config import settings

if False:
    libdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'lib')
    if os.path.exists(libdir):
        sys.path.append(libdir)

    import logging
    from waveshare_epd import epd7in3f
    from PIL import Image,ImageDraw,ImageFont
    import traceback


logging.basicConfig(level=logging.DEBUG)

celery = Celery(
    __name__,
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

paused = False
generate_image_process = None

@celery.task(base=Singleton)
def generate_image(prompt: str, output_file_path: str):
    path = Path(output_file_path)
    seed = random.randint(0, 1000000)
    
    if False:
        command = './sd --turbo --prompt {} --models-path sdxlturbo --steps 1 --output {} --seed {}'.format(quote(prompt), quote(output_file_path), seed)\
    else:
        command = 'sleep 1000'
    
    global generate_image_process
    generate_image_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    while True:
        output_line = generate_image_process.stdout.readline()
        if output_line == '' and generate_image_process.poll() is not None:
            break

        logging.info("Output:", output_line.strip())

        error_line = generate_image_process.stderr.readline()
        if error_line == '' and generate_image_process.poll() is not None:
            break

        logging.info("Error:", error_line.strip())

    generate_image_process.wait()
    
    with open(path.parent / "data.txt", "wa") as f:
        f.write("{} {} {}\n".format(path.stem, prompt, seed))
    
@celery.task(base=Singleton)
def cancel_generate_image():
    if generate_image_process is not None:
        generate_image_process.kill()
    
@celery.task
def generate_prompts(amount: int):
    with open('data/prompt_data.txt') as f:
        lines = [x.strip() for x in f.readlines()]
        prompts = [", ".join([random.choice(lines) for ii in random.randrange(3,8)]) for i in range(amount)]
        return prompts

palette = np.array([
    [0, 0, 0],       # Black
    [0, 0, 255],     # Blue
    [255, 0, 0],     # Red
    [0, 255, 0],     # Green
    [255, 128, 0],   # Orange
    [255, 255, 0],   # Yellow
    [255, 255, 255], # White
])

def find_closest_color(pixel, palette):
    distances = np.linalg.norm(palette - pixel, axis=1)
    return np.argmin(distances)

@celery.task
def dither_image(image_path: str, output_path: str):
    # Load the image
    image = Image.open(image_path)

    # Convert the image to a NumPy array
    img_array = np.array(image)

    # Normalize pixel values to the range [0, 1]
    img_array = img_array / 255.0

    # Apply Floyd-Steinberg dithering using the specified palette
    for y in range(img_array.shape[0] - 1):
        for x in range(1, img_array.shape[1] - 1):
            old_pixel = img_array[y, x]
            new_pixel_index = find_closest_color(old_pixel, palette)
            new_pixel = palette[new_pixel_index]
            img_array[y, x] = new_pixel
            error = old_pixel - new_pixel

            img_array[y, x + 1] += error * 7 / 16
            img_array[y + 1, x - 1] += error * 3 / 16
            img_array[y + 1, x] += error * 5 / 16
            img_array[y + 1, x + 1] += error * 1 / 16

    # Convert the NumPy array back to an image
    dithered_image = Image.fromarray((img_array * 255).astype(np.uint8))

    # Save the dithered image
    dithered_image.save(output_path)

@celery.task
def draw_image(file_path: str):
    try:
        epd = epd7in3f.EPD()
        logging.info("init and Clear")
        epd.init()
        epd.Clear()

        Himage = Image.open(file_path)
        epd.display(epd.getbuffer(Himage))
        epd.sleep()

    except Exception as e:
        logging.info("Goto Sleep...")
        epd.sleep()

        logging.info("ctrl + c:")
        epd7in3f.epdconfig.module_exit()

        logging.info(e)
         
@celery.task
def start():
    while True:
        generate_image.map(generate_prompts()).get()
    
start()