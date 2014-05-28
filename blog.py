import fix_path
import urllib2
import webapp2
import os
import jinja2
import re
import hashlib
import hmac
import random
import string
import logging
import json
import time

#initiating the logger for degugging
logging.getLogger().setLevel(logging.DEBUG)

from google.appengine.ext import db
from google.appengine.api import memcache
from google.appengine.api import images
import secret

secret = secret.secret

#this part here loads up the templates from the given directory 
template_dir = os.path.join(os.path.dirname(__file__), 'blog_templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
                                autoescape = False)

#this function uses the Github's markdown api to apply markdown on the post for the blog
def markDown(to_mark):
     headers = {
         'content-type': 'application/json'
     }
     #text = to_mark.decode('utf8')
     payload = {
         'text': to_mark,
         'mode':'gfm'
     }
     data = json.dumps(payload)
     req = urllib2.Request('https://api.github.com/markdown', data, headers)
     response = urllib2.urlopen(req)
     marked_down = response.read().decode('utf8') #no idea why this works, will have to look it up
     return marked_down

#this is where the database is created. GAE running on python
#needs a class to be defined inheriting the db.model method/class
class Blog(db.Model):
    subject = db.StringProperty(required = True, multiline = True)
    blog = db.TextProperty(required = True)
    time_created = db.DateTimeProperty(auto_now_add = True)
    day_created = db.DateProperty(auto_now_add = True)
    post_slice = db.TextProperty()
    tags = db.StringListProperty(str, default = None)


#makes a hash of the password
def make_pw_h(name, pw):
    return "%s" % (hashlib.sha256(name + pw).hexdigest())

#checks whether the password is proper or not
def check_pw_h(name, pw, h):
    #h = h.split(',')[1]
    return h == make_pw_h(name, pw)

#creates a db for users
class Users(db.Model):
    username = db.StringProperty(required = True)
    pw_hash = db.StringProperty(required = True)
    email = db.StringProperty()
    user_since = db.DateTimeProperty(auto_now_add = True)

    @classmethod
    def by_id(cls, uid):
        return Users.get_by_id(uid)

    @classmethod
    def by_name(cls, name):
        user = Users.all().filter('name = ', name).get()
        return user

    @classmethod
    def register(cls, name, pw, email = None):
        pw_h = make_pw_h(name, pw)
        return Users(username = name,
                    pw_hash = pw_h,
                    email = email)

    @classmethod
    def login(cls, name, pw):
        u = cls.by_name(name)
        if u and check_pw(pw):
            return u        

class Images(db.Model):
    name = db.StringProperty()
    image = db.BlobProperty(default=None)


#a simple funcion to render the template
def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)

def make_secure_val(val):
    return '%s|%s' % (val, hmac.new(secret, val).hexdigest())

def check_secure_val(sec_val):
    val = sec_val.split('|')[0]
    if sec_val == make_secure_val(val):
        return val


#this is the superclass which all other classes use in the file
class BaseHandler(webapp2.RequestHandler):

    #funcion to render the template    
    def render(self, template, **kw):
        self.response.out.write(render_str(template, **kw))

    #making a simpler way to send html
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    #setting a cookie
    def set_sec_coki(self, name, val):
        sec_val = make_secure_val(str(val))
        self.response.headers.add_header('Set-Cookie', "%s=%s; Path=/" % (name, sec_val))

    #reading a secure cookie and cheking if it is valid
    def read_secure_cookie(self, name):
        cookie_val = self.request.cookies.get(name)
        return cookie_val and check_secure_val(cookie_val)

    #checking if the user is logged in so that I can display username on page at
    #all times
    def checkLogin(self):
        cookie = self.request.cookies.get('user-id')
        if cookie:
            return True
        else:
            return False

    #function to log a user in
    def login(self, user):
        self.set_secure_cookie('user_id', str(user.key().id()))

    #function to log a user out
    def logout(self):
        self.response.delete_cookie('user-id')

    def Initialize(self, *a, **kw):
        webapp2.RequestHandler.Initialize(self, *a, **kw)
        uid = self.read_sec_coki('user-id')
        self.user = uid and Users.by_id(int(uid))

    # This function is used to check whether a user is logged in and whether
    # or not he/she exists.
    def check_user(self):
        userLogin = self.checkLogin()
        cookieVal = self.read_secure_cookie('user-id')
        name = ""
        if cookieVal:
           u_id = cookieVal.split('|')[0]
           usr_instance = Users.get_by_id(int(u_id))
           name = usr_instance.username
        
        return userLogin, name
        


# Creating a function for querying the db for blog posts and when invoked 
# with Blog_posts(True) Update is set to True
def Blog_posts(Update = False):
    key = 'post1'
    posts = memcache.get(key)
    if posts is None or Update:
        logging.info("DB Query for posts")
        posts = db.GqlQuery('SELECT * FROM Blog ORDER BY time_created DESC')
        memcache.set(key, posts)
    return posts

#Creating a function for slicing the first 100 characters of the blog
def slice_post(post):
    return post[:150]

#Straight up querying up blog posts and displaying them
class Mainpage(BaseHandler):
    def get(self):
        posts = Blog_posts()
        userLogin, name = self.check_user()
        # Creating a dictionary of jinja2 parameters
        params = {
            'posts': posts,
            'userLogin': userLogin,
            'user_name': name,
        }

        if userLogin == True and name:
            self.render("blog.html", **params)
        else:
            params['user_name'] = ""
            self.render("blog.html", **params)


#this class handles the newpost page which is  
#inserting into a database the subject, text, time
#and maybe the author of the blog post

class Newpost(BaseHandler):

    #the form is being rendered at a lot of  
    #places so to make sure that there is no 
    #duplication of the logic, this function is used
    #to note-we are writing over the parts where I placed the templates in the html file

    def render_form(self, subject="", blog="", error=""): 
        userLogin, name = self.check_user()
        if userLogin == True and name:
            params = {
                'subject': subject,
                'blog': blog,
                'error': error,
                'userLogin': userLogin,
                'user_name': name,
            }
            self.render("submit.html", **params)

    #this is just the function which responds to the GET call
    def get(self):
        cookieVal = self.request.cookies.get('user-id')
        if cookieVal == None:
            self.redirect('/blog')
        else :
            self.render_form()            

    #this is where all the computation for the form is done
    def post(self):
        #getting the required parameters from the form
        tag_list = []
        subject = self.request.get("subject")
        blog = self.request.get("content")
        tags = self.request.get("tags")

        tag_list = tags.split()
        _slice = slice_post(blog) + "..."

        if subject and blog: #need both the fields to be filled in order to get accepted
            mark_blog = markDown(blog)
            mark_slice = markDown(_slice)
            post = Blog(subject = subject, blog = mark_blog,
                        post_slice = mark_slice, tags = tag_list)
            post_key = post.put()
            Blog_posts(True)
            self.redirect('/blog/%d' % post_key.id())

        else:
            error = "Both subject and the blogpost sections are to filled"
            self.render_form(subject, blog, error)


#this handles permalinks
class Permalink(BaseHandler):
    def get(self, post_id):        
        userLogin, name = self.check_user()

        #Checing if the post is in the cache

        key = post_id
        part_post = memcache.get(key)
        if part_post : 
            post_sub = part_post.subject
            post_blog = part_post.blog
            post_date = part_post.day_created
            params = {
                'subject': post_sub,
                'blog': post_blog,
                'id': post_id,
                'day': post_date,
                'userLogin': userLogin,
                'user_name': name,
                'post_id': post_id,

            }
            if userLogin == True and name:
                self.render("link.html", **params)
            else:
                params['user_name'] = ""
                self.render("link.html", **params)
                
        else:

        #Creating a memcache entry with key as post id          

            part_post = Blog.get_by_id(int(post_id))
            post_sub = part_post.subject
            post_blog = part_post.blog
            post_date = part_post.day_created
            memcache.set(key, part_post)
            params = {
                'subject': post_sub,
                'blog': post_blog,
                'id': post_id,
                'day': post_date,
                'userLogin': userLogin,
                'user_name': name,
                'post_id': post_id,

            }
            if userLogin == True and name:
                self.render("link.html", **params)
            else:
                params['user_name'] = ""
                self.render("link.html", **params)


USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")
def valid_username(username):
    if Users.all().filter('name = ', username).get():
        return False
    else:
        return username and USER_RE.match(username)

PASS_RE = re.compile(r"^.{3,20}$")
def valid_password(password):
    return password and PASS_RE.match(password)

EMAIL_RE = re.compile(r'^[\S]+@[\S]+\.[\S]+$')
def valid_email(email):
    return not email or EMAIL_RE.match(email)
#need to re implement the entire signup page

class SignupHandler(BaseHandler):
    def get(self):
        self.render('signup-form.html')

    def post(self):
        username = self.request.get('username')
        password = self.request.get('password')
        verify = self.request.get('verify')
        email = self.request.get('email')

        has_error = False
        error = {}

        params = {
            'username': username,
            'error':"",
        }

        if username:
            if valid_username(username):
                pass
            else:
                has_error = True
                params[error["error_username"]] = "Invalid username"
                self.render('signup-form.html', **params)
        else:
            has_error = True
            params[error["error_username"]] = "Enter a username"
            self.render('signup-form.html', **params)


        if password or verify:
            if valid_password(password):
                pass
            else:
                has_error = True
                params[error["error_password"]] = "Enter a valid password"
                self.render('signup-form.html', **params)
        if password != verify:
            has_error = True
            params[error["error_password"]] = "Passwords do not match"
            self.render('signup-form.html', **params)

        if email:
            if valid_email(email):
                pass
            else:
                params[error["error_email"]] = "enter a valid email"
                self.render('signup-form.html', **params)

        if has_error == False:
            if email:
                user = Users(username = username, pw_hash = make_pw_h(username, password) ,email = email)
            else:
                user = Users(username = username, pw_hash = make_pw_h(username, password))

            user.put()
            self.set_sec_coki('user-id', user.key().id())
            self.redirect('/blog')




#This class takes care of the login funcionalities for the user
class Login(BaseHandler):
    def get(self):
        self.render('login-form.html')

    def post(self):
        #getting the username and password that the user entered
        self.username = self.request.get('username')
        self.password = self.request.get('password')
        #checking if user exists
        user = db.GqlQuery("SELECT * FROM Users WHERE username = :1", self.username).get()
        #checking if the password is correct
        if user:
            check = check_pw_h(self.username, self.password, user.pw_hash)        
            if check:
                #setting the user's cookie
                self.set_sec_coki('user-id', user.key().id())
                self.redirect('/blog')
            else:
                msg = 'Invalid login'
                self.render('login-form.html', error = msg)
        else:
            msg = 'Invalid login'
            self.render('login-form.html', error = msg)

#This class handles the logging out of users. It simply
#clears the cookie and redirects to the mainpage
class Logout(BaseHandler):
    def get(self):
        self.logout()
        self.redirect('/blog')
                
#This class handles exporting the main blog page to JSON        
class JSONMainPageHandler(BaseHandler):
     def get(self):
         self.response.headers['Content-Type'] = 'application/json'
         #Getting all the entries of the page
         posts = Blog_posts()
         logging.info(int(posts.count())) 
         #Looping through them all to get the JSON text
         json_text = {}
         json_data = {}
         for index, post in enumerate(posts, 1):
             json_data["post{}".format(index)] = {
                 'subject': post.subject,
                 'content': post.blog,
                 'day'    : post.day_created.strftime('%d %b %Y')
             }

         json_text = json.dumps(json_data)        

         self.write('{"allposts":'+json_text+'}')

#This class handles exporting permalinks to JSON
class JSONPermalinkHandler(BaseHandler):
     def get(self, post_id):
         self.response.headers['Content-Type'] = 'application/json'
         json_data = {}
         post = Blog.get_by_id(int(post_id))
         json_data["post{}".format(post_id)] = {
             'subject': post.subject,
             'content': post.blog,
             'day'    : post.day_created.strftime("%d %b %Y")
         }
         json_text = json.dumps(json_data)
         self.write(json_text)

class HomePage(BaseHandler):
   def get(self):
    self.render('home.html')

class ProjectsPage(BaseHandler):
    def get(self):
        self.render('projects.html')

# This is a very simple archive. It is a list of all the articles in descending order.
class ArchiveManager(BaseHandler):
    def get(self):
        posts = Blog_posts()
        userLogin, name = self.check_user()
        params = {
            'posts': posts,
            'userLogin': userLogin,
            'user_name': name,
        }
        if userLogin == True and name:
            self.render("archive.html", **params)
        else:
            params['user_name']= ""
            self.render("archive.html", **params)

class Editor(BaseHandler):
    # Getting the particular post from the database by the GET parameters

    def get(self, post_id):
        post = Blog.get_by_id(int(post_id))
        post_subject = post.subject
        post_text = post.blog
        post_tags = post.tags
        logging.info(post_tags )
        self.render("edit.html", subject = post.subject, text = post_text, tags = post_tags)

    # Getting the same post from the post_id and updating the fields and putting it back in the database
    def post(self, post_id):
        tags_list = []
        subject = self.request.get("subject")
        blog = self.request.get("content")
        tags = self.request.get("tags")
        logging.info(tags)

        _slice = slice_post(blog) + "..."
        mark_blog = markDown(blog)
        mark_slice = markDown(_slice)
        tags_list = tags.split()

        post = Blog.get_by_id(int(post_id))
        post.subject = subject
        post.blog = mark_blog
        post.post_slice = mark_slice
        post.tags = tags_list
        post.put()
        Blog_posts(True)
        self.redirect('/blog')


class TagsHandler(BaseHandler):
    def get(self):
        userLogin, name = self.check_user()
        tags = self.request.GET["tag"]
        posts = db.GqlQuery(" SELECT * FROM Blog WHERE tags = :1 ORDER BY time_created DESC", tags)
        params = {
            'posts': posts,
            'userLogin': userLogin,
            'name': name,
            'tag': tags,
        }
        if userLogin == True and name:
            self.render("tags.html", **params)
        else:
            params['user_name'] = ""
            self.render("tags.html", **params)

class ImageUploader(BaseHandler):
    def get(self):
        userLogin, name = self.check_user()
        if userLogin == True and name:
            self.render("image-upload.html", userLogin = userLogin, name = name)
        else:
            self.redirect('/blog')

    def post(self):
        Image = Images()
        title = self.request.get('img-name')
        image = self.request.get('img')
        image = images.resize(image, 1000, 600)
        Image.name = title
        Image.image = db.Blob(image)
        Image.put()
        self.redirect('/images?id=%s' % Image.key().id())   
        
class ImageHandler(BaseHandler):
    def get(self):
        userLogin, name = self.check_user()
        img_id = self.request.GET["id"]
        logging.info(name)
        image = Images.get_by_id(int(img_id))
        logging.info(image)
        if image.image:
            self.response.headers['Content-Type'] = 'image/jpeg'
            self.response.out.write(image.image)
        # else:
        #     self.redirect('/static/images/rainbow.jpg')


#this describes the url handlers
app = webapp2.WSGIApplication([('/',HomePage),
                               ('/blog', Mainpage),
                               ('/projects', ProjectsPage),
                               ('/archive', ArchiveManager),
                               ('/blog/newpost', Newpost),
                               ('/blog/(\d+)',Permalink),
                               ('/blog/_admin/signup', SignupHandler),
                               ('/blog/_admin/login', Login),
                               ('/logout', Logout),
                               ('/blog.json',JSONMainPageHandler),
                               ('/blog/(\d+).json', JSONPermalinkHandler),
                               ('/edit/(\d+)', Editor),
                               ('/tags?[a-zA-Z0-9=+]*$', TagsHandler),
                               ('/img', ImageUploader),
                               ('/images?[a-zA-Z0-9=+]*$', ImageHandler),
                               ], debug = True)
