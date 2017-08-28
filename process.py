from PIL import Image,ImageStat

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.colors import Color, HexColor
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfgen import canvas
import logging, itertools
import os
MAX = 1200

log = logging.getLogger('auto_layout')
log.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
sh = logging.StreamHandler()
sh.setFormatter(formatter)
log.addHandler(sh)

class Photo(object):

    def __init__(self, f):

        self.f = f
        _i = open(f,'r')
        self.img = Image.open(_i)
        self.stat = s = ImageStat.Stat(self.img)

        self.w, self.h = self.img.size
        self.placed = False
        self.drawn = False
        self.scale = 1.0

        AVG=0.1
        self.data = self.img.load()
        # top_avg = self.get_average_color(0, 0, self.w, self.h * AVG)
        # bot_avg = self.get_average_color(0, self.h * (1 - AVG), self.w, self.h * AVG)
        # left_avg = self.get_average_color(0, 0, int(self.w * AVG)-1, self.h)
        # right_avg = self.get_average_color(0, int(self.w * (1 - AVG))-1, int(self.w * AVG)-1, self.h)

        self.order = sum(s.mean)/3


    def get_average_color(self, top, left, width, height):
        """ Returns a 3-tuple containing the RGB value of the average color of the
        given square bounded area of length = n whose origin (top left corner)
        is (x, y) in the given image"""


        r, g, b = 0, 0, 0
        count = 0

        for t in range(top, top + height):
            for s in range(left, left + width):
                try:
                    pixlr, pixlg, pixlb = self.data[s, t]
                except IndexError:
                    print '{},{} in image size {},{}'.format(s,t, self.w, self.h)
                    raise
                except:
                    print 'Error in {}'.format(self)
                    raise

                r += pixlr
                g += pixlg
                b += pixlb
                count += 1
        return ((r / count), (g / count), (b / count))


    def __repr__(self):
        return '<"{}" {}x{}>'.format(self.f, self.w, self.h)

class Photos(object):

    def __init__(self, root):
        self.photos = photos = []

        for path,dir,files in os.walk(root):

            for fl in files:
                if 'rms' in path:
                    continue

                f = os.path.join(path,fl)
                try:
                    photos.append(Photo(f))
                    if len(photos) > MAX:
                        break
                except IOError:
                    pass


        log.debug('{} files read'.format(len(photos)))
        self.extents()
        self.sorted = sorted(self.photos, key=lambda p:p.order, reverse=True)

    def extents(self):
        log.debug( 'height: {} to {}'.format(
            min(map(lambda _:_.h, self.photos)),
            max(map(lambda _:_.h, self.photos))
        ))
        log.debug( 'width: {} to {}'.format(
            min(map(lambda _:_.w, self.photos)),
            max(map(lambda _:_.w, self.photos))
        ))

    def reset_undrawn(self):
        for p in filter(lambda _:_.placed is True and _.drawn is False, photos.photos):
            p.placed = False

    def unplaced(self):
        return filter(lambda _:_.placed is False, photos.sorted)


def debug_var(**kwargs):
    for k,v in kwargs.iteritems():
        log.debug('{}={}'.format(k,v))

total_w = lambda photos: sum(map(lambda _:_.w*_.scale, photos))

def photo_variance(photos):

    total = sum(map(lambda _:_.scale, photos))
    avg = total/len(photos)

    diffs = 0

    for p in photos:
        diffs += abs(avg - p.scale)

    return pow(diffs, 2)/len(photos)

class PDF(object):


    MIN_ROWS_PER_PAGE = 2

    def __init__(self, f, page, inset_tbo, inset_b, DPI, photos):
        """
        :param inset_tbo: top bottom outside
        :param inset_b:  binding edge
        """

        points_w, points_h = page
        self.c = canvas.Canvas(f, pagesize=(points_w, points_h))
        self.photos = photos

        #odd pages have the binding on the left, even on the right
        self.page = 1

        #"points" - 72 DPI is the baseline
        self.points_w = points_w
        self.points_h = points_h

        #ratio is pixels per point
        self.DPI = DPI
        self.ratio = DPI/72.0

        #pixels are page size minus inset
        self.page_px_w = (points_w - inset_tbo - inset_b)* self.ratio
        self.page_px_h = (points_h - inset_tbo * 2)* self.ratio
        self.inset_tbo = inset_tbo
        self.inset_b = inset_b

    def scale_row(self, photos, desired=None):
        """
        apply a scale factor to every photo so that it is the same height as the shortest photo in the row
        """

        min_height = float(min(map(lambda _:_.h, photos)))

        min_height = min(self.page_px_h/self.MIN_ROWS_PER_PAGE, min_height)

        if desired is not None:
            min_height=desired

        for p in photos:
            p.scale = min_height / p.h
            log.debug('{} scaled to {}'.format(p, p.scale))

        return total_w(photos)

    def draw_row(self, top, draw, photos):

        local_scale=1

        for photo in self.photos.unplaced():

            local_scale = self.scale_row(photos + [photo])

            # if all(map(lambda _: _.scale > 0.8, photos + [photo])):
            # if photo_variance(photos + [photo]) < 0.05:
            if True:
                photos.append(photo)


                if local_scale >= self.page_px_w:
                    break
            # log.debug('scale variance is {}'.format(photo_variance(photos)))

        assert photos
        scale = 1.0 / (local_scale / self.page_px_w)
        row_height = photos[0].h * photos[0].scale * scale

        left = (self.inset_tbo if self.page % 2==0 else self.inset_b) * self.ratio

        for p in photos:
            left = self.draw_jpg(p, left, top, scale=scale, draw=draw)
            p.placed = True

        return row_height + top

    def draw_page(self):

        top = 0
        last_top = 0
        rows = 0
        colours = []

        while True:
            photos = []
            top = self.draw_row(top, draw=False, photos=photos)
            if top < self.page_px_h:
                rows += 1
                last_top = top
                colours.extend(map(lambda _:_.stat.median, photos))
            else:
                break

        r = sum(map(lambda _:_[0], colours))/len(colours)/255.0
        try:
            g = sum(map(lambda _:_[1], colours))/len(colours)/255.0
            b = sum(map(lambda _:_[2], colours))/len(colours)/255.0
        except IndexError:
            g = b = r
        fill = Color(r,g,b)
        self.add_blank(fill)
        self.photos.reset_undrawn()
        diff= (self.page_px_h-last_top)/(rows+1)
        debug_var(
            last_top =last_top,
            top = top,
            diff=diff
        )
        top = diff - self.inset_tbo*self.ratio
        while rows > 0:
            photos=[]
            top = self.draw_row(top, draw=True, photos=photos)+diff
            rows -= 1


        self.c.showPage()
        self.page += 1
        return fill

    def add_blank(self, fill):
        self.c.setFillColor(fill)
        path = self.c.beginPath()
        path.moveTo(0 * cm, 0 * cm)
        path.lineTo(0 * cm, 30 * cm)
        path.lineTo(25 * cm, 30 * cm)
        path.lineTo(25 * cm, 0 * cm)
        self.c.drawPath(path, True, True)

    def convert_h_px(self, px):
        return px/self.ratio

    def convert_w_px(self, px):
        return px/self.ratio

    def draw_jpg(self, p, left=0, top=0, scale=0.5, draw=False):

        #we need width and height in points...

        w=p.w*scale*p.scale
        h=p.h*scale*p.scale

        assert w and h, 'Photo {} {} {}'.format(w, h, p)

        bottom = self.page_px_h - top - h

        if draw:
            self.c.drawImage(p.f, self.convert_w_px(left), self.convert_h_px(bottom), self.convert_w_px(w), self.convert_h_px(h))
            p.drawn = True
        return w + left

    def render_pdf(self):
        self.c.save()

if True:
    photos = Photos('./photos')
    page_w, page_h = A4
    pdf = PDF('./output.pdf', page=(621, 810), inset_tbo=18, inset_b=45, DPI=132, photos=photos)
    while True:
        try:
            colour = pdf.draw_page()
        except AssertionError:
            break
    for i in range(pdf.page % 4+1):
        pdf.add_blank(colour)
        pdf.c.showPage()
    pdf.render_pdf()
    print pdf.page

class Cover(PDF):

    def render_pdf(self):
        self.c.showPage()
        self.c.showPage()
        self.c.save()

cover = Cover('./cover.pdf', page=(1269, 810), inset_b=0, inset_tbo=0, DPI=0, photos=[])
cover.render_pdf()

