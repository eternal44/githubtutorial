from string import join
from collections import defaultdict

from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import get_object_or_404, render_to_response
from django.contrib.auth.decorators import login_required
from django.core.context_processors import csrf
from django.core.paginator import Paginator, InvalidPage, EmptyPage
from django.db.models import Q
from django.contrib.auth.models import User
from django import forms

from dbe.photo.models import *
from settings import MEDIA_URL


class SearchForm(forms.Form):
    """"""
    def __init__(self, *args, **kwargs):
        super( MyForm, self ).__init__( *args, **kwargs )
        self.fields['albums'] = forms.MultipleChoiceField(
            choices=[(o.id, str(o)) for o in Album.objects.all()] )
        self.fields['users'] = forms.MultipleChoiceField(
            choices=[(o.id, str(o)) for o in User.objects.all()] + ["all"] )

    title = forms.CharField(required=False)
    filename = forms.CharField(required=False)
    tags = forms.CharField(required=False)

    rating_from = forms.CharField(required=False, max_length=3)
    rating_to = forms.CharField(required=False, max_length=3)
    width_from = forms.CharField(required=False, max_length=3)
    width_to = forms.CharField(required=False, max_length=3)
    height_from = forms.CharField(required=False, max_length=3)
    height_to = forms.CharField(required=False, max_length=3)

    mode = forms.ChoiceField(choices=[("view", "view"), ("edit", "edit")])
    sort = forms.ChoiceField(choices=[("date", "date"), ("rating", "rating") ("width", "width"),
                                     ("height", "height") ])
    asc_desc = forms.ChoiceField(choices=[("asc", "ascending"), ("desc", "descending")])


def main(request):
    """Main listing."""
    albums = Album.objects.all()
    if not request.user.is_authenticated():
        albums = albums.filter(public=True)
    paginator = mk_paginator(request, albums, 10)
    return render_to_response("photo/list.html", dict(albums=paginator, user=request.user,
                                                      media_url=MEDIA_URL))

def mk_paginator(request, items, num_items):
    """Create and return a paginator."""
    paginator = Paginator(items, 10)
    try: page = int(request.GET.get("page", '1'))
    except ValueError: page = 1

    try:
        items = paginator.page(page)
    except (InvalidPage, EmptyPage):
        items = paginator.page(paginator.num_pages)
    return items

def image(request, pk):
    """Image page."""
    return render_to_response("photo/image.html", dict(image=Image.objects.get(pk=pk), user=request.user,
                                            backurl=request.META["HTTP_REFERER"], media_url=MEDIA_URL))

@login_required
def search(request):
    if request.method == "POST":
        f = SearchForm(request.POST)
        if f.is_valid():


@login_required
def search2(request):
    """Search, filter, sort images."""
    try: page = int(request.GET.get("page", '1'))
    except ValueError: page = 1

    p = request.POST
    images = defaultdict(dict)

    # init parameters
    parameters = {"album": []}
    keys = ("title filename rating_from rating_to width_from width_to height_from height_to tags view"
        " user sort asc_desc").split()
    for k in keys: parameters[k] = ''

    # create dictionary of properties for each image and a dict of search/filter parameters
    for k, v in p.items():
        if k == "album":
            parameters[k] = [int(x) for x in p.getlist(k)]
        elif k == "user":
            if v != "all": v = int(v)
            parameters[k] = v
        elif k in parameters:
            parameters[k] = v
        elif k.startswith("title") or k.startswith("rating") or k.startswith("tags"):
            k, pk = k.split('-')
            images[pk][k] = v
        elif k.startswith("album"):
            pk = k.split('-')[1]
            images[pk]["albums"] = p.getlist(k)

    # save or restore parameters from session
    s = request.session
    if page != 1 and "parameters" in s: parameters = s["parameters"]
    else: s["parameters"] = parameters

    results = update_and_filter(request, images, parameters)
    paginator = mk_paginator(request, results, 20)

    d = dict(results=paginator, user=request.user, albums=Album.objects.all(), prm=parameters,
             users=User.objects.all(), media_url=MEDIA_URL)
    d.update(csrf(request))
    return render_to_response("photo/search.html", d)

def update_and_filter(request, images, p):
    """Update image data if changed, filter results through parameters and return results list."""
    # process properties, assign to image objects and save
    for k, d in images.items():
        image = Image.objects.get(pk=k)
        image.title = d["title"]
        image.rating = int(d["rating"])

        # tags - assign or create if a new tag!
        tags = d["tags"].split(', ')
        lst = []
        for t in tags:
            if t: lst.append(Tag.objects.get_or_create(tag=t)[0])
        image.tags = lst

        if "albums" in d:
            image.albums = d["albums"]
        image.save()

    # sort and filter results by parameters
    order = "created"
    if p["sort"]: order = p["sort"]
    if p["asc_desc"] == "desc": order = '-' + order

    results = Image.objects.all().order_by(order)
    if p["title"]       : results = results.filter(title__icontains=p["title"])
    if p["filename"]    : results = results.filter(image__icontains=p["filename"])
    if p["rating_from"] : results = results.filter(rating__gte=int(p["rating_from"]))
    if p["rating_to"]   : results = results.filter(rating__lte=int(p["rating_to"]))
    if p["width_from"]  : results = results.filter(width__gte=int(p["width_from"]))
    if p["width_to"]    : results = results.filter(width__lte=int(p["width_to"]))
    if p["height_from"] : results = results.filter(height__gte=int(p["height_from"]))
    if p["height_to"]   : results = results.filter(height__lte=int(p["height_to"]))
    if p["user"] and p["user"] != "all"    : results = results.filter(user__pk=int(p["user"]))

    if p["tags"]:
        tags = p["tags"].split(', ')
        lst = []
        for t in tags:
            if t:
                results = results.filter(tags=Tag.objects.get(tag=t))

    if p["album"]:
        lst = p["album"]
        or_query = Q(albums=lst[0])
        for album in lst[1:]:
            or_query = or_query | Q(albums=album)
        results = results.filter(or_query).distinct()
    return results

def update(request):
    """Update image title, rating, tags, albums."""
    p = request.POST
    images = defaultdict(dict)

    # create dictionary of properties for each image
    for k, v in p.items():
        if k.startswith("title") or k.startswith("rating") or k.startswith("tags"):
            k, pk = k.split('-')
            images[pk][k] = v
        elif k.startswith("album"):
            pk = k.split('-')[1]
            images[pk]["albums"] = p.getlist(k)

    # process properties, assign to image objects and save
    for k, d in images.items():
        image = Image.objects.get(pk=k)
        image.title = d["title"]
        image.rating = int(d["rating"])

        # tags - assign or create if a new tag!
        tags = d["tags"].split(', ')
        lst = []
        for t in tags:
            if t: lst.append(Tag.objects.get_or_create(tag=t)[0])
        image.tags = lst

        if "albums" in d:
            image.albums = d["albums"]
        image.save()

    return HttpResponseRedirect(request.META["HTTP_REFERER"], dict(media_url=MEDIA_URL))

def album(request, pk, view="thumbnails"):
    """Album listing."""
    num_images = 30
    if view == "full": num_images = 10

    album = Album.objects.get(pk=pk)

    if not album.public and not request.user.is_authenticated():
        return HttpResponse("Error: you need to be logged in to view this album.")

    images = album.image_set.all()

    paginator = mk_paginator(request, images, num_images)

    # add list of tags as string and list of album names to each image object
    for img in paginator.object_list:
        tags = [x[1] for x in img.tags.values_list()]
        img.tag_lst = join(tags, ', ')
        img.album_lst = [x[1] for x in img.albums.values_list()]

    d = dict(album=album, images=paginator, user=request.user, view=view, albums=Album.objects.all(),
            media_url=MEDIA_URL)
    d.update(csrf(request))
    return render_to_response("photo/album.html", d)
