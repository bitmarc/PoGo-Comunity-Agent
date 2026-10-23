"""Genera public/login.png: el bot de HXQ con el titulo debajo, sobre fondo de marca.

Chainlit muestra esa imagen en el panel del login con `object-cover`, asi que se
recorta por los lados en pantallas estrechas: todo lo importante va en el centro.

Pillow no es dependencia del proyecto; se trae solo para correr esto:
    uv run --no-project --with pillow python scripts/generar_login.py
"""

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1200, 1400
BASE = (17, 16, 28)


def resplandor(color, centro, radio, alfa):
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    x, y = centro
    d.ellipse((x - radio, y - radio, x + radio, y + radio), fill=(*color, alfa))
    return capa.filter(ImageFilter.GaussianBlur(radio * 0.6))


# Fondo: base oscura con los tres resplandores del login anterior (verde arriba,
# magenta a la derecha, teal abajo a la izquierda) y uno teal suave detras del bot.
fondo = Image.new("RGBA", (W, H), (*BASE, 255))
for color, centro, radio, alfa in [
    ((48, 140, 62), (600, 150), 420, 110),
    ((150, 30, 80), (1150, 900), 380, 90),
    ((3, 136, 166), (120, 1300), 380, 80),
    ((3, 136, 166), (600, 640), 330, 70),
]:
    fondo = Image.alpha_composite(fondo, resplandor(color, centro, radio, alfa))

# Bot centrado, con un halo claro para separarlo del fondo.
bot = Image.open("docs/marca/bot-hxq.png").convert("RGBA")
lado = 640
bot = bot.resize((lado, lado), Image.LANCZOS)
bx, by = (W - lado) // 2, 250
halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
mascara = bot.split()[3].point(lambda a: 120 if a > 40 else 0)
halo.paste(Image.new("RGBA", (lado, lado), (34, 211, 238, 255)), (bx, by), mascara)
fondo = Image.alpha_composite(fondo, halo.filter(ImageFilter.GaussianBlur(28)))
fondo.alpha_composite(bot, (bx, by))

# Titulo en Baloo 2 ExtraBold, blanco con resplandor cian como los titulos de las piezas.
fuente = ImageFont.truetype("src/hxq_agent/brand/fonts/Baloo2.ttf", 100)
fuente.set_variation_by_axes([800])  # eje de peso de la fuente variable
texto = "Huixqui-GO Agent"
caja = ImageDraw.Draw(fondo).textbbox((0, 0), texto, font=fuente)
tw = caja[2] - caja[0]
tx, ty = (W - tw) // 2 - caja[0], by + lado - 10

brillo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
ImageDraw.Draw(brillo).text((tx, ty), texto, font=fuente, fill=(34, 211, 238, 230))
fondo = Image.alpha_composite(fondo, brillo.filter(ImageFilter.GaussianBlur(14)))
d = ImageDraw.Draw(fondo)
d.text(
    (tx, ty),
    texto,
    font=fuente,
    fill=(255, 255, 255, 255),
    stroke_width=2,
    stroke_fill=(3, 136, 166, 255),
)

fondo.convert("RGB").save("public/login.png", optimize=True)
print("login.png", fondo.size, "texto", tw, "px de ancho")
