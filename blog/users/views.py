
from django.shortcuts import render

# Create your views here.
from django.shortcuts import render
from django.urls import reverse
# Create your views here.
import re
from django.views import View
from users.models import User
from django.db import DatabaseError
from django.http.response import HttpResponseBadRequest
from libs.captcha.captcha import captcha
from django_redis import get_redis_connection
from django.http import HttpResponse
from django.shortcuts import  redirect


#注册视图
class RegisterView(View):

    def get(self,request):

        return render(request,'register.html')

    def post(self, request):
        """
        1.接收数据
        2.验证数据
            2.1 参数是否齐全
            2.2 手机号的格式是否正确
            2.3 密码是否符合格式
            2.4 密码和确认密码要一致
            2.5 短信验证码是否和redis中的一致
        3.保存注册信息
        4.返回响应跳转到指定页面
        :param request:
        :return:
        """
        # 1.接收数据
        mobile = request.POST.get('mobile')
        password = request.POST.get('password')
        password2 = request.POST.get('password2')
        smscode = request.POST.get('sms_code')
        # 2.验证数据
        #     2.1 参数是否齐全
        if not all([mobile, password, password2, smscode]):
            return HttpResponseBadRequest('缺少必要的参数')
        #     2.2 手机号的格式是否正确
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return HttpResponseBadRequest('手机号不符合规则')
        #     2.3 密码是否符合格式
        if not re.match(r'^[0-9A-Za-z]{8,20}$', password):
            return HttpResponseBadRequest('请输入8-20位密码，密码是数字，字母')
        #     2.4 密码和确认密码要一致
        if password != password2:
            return HttpResponseBadRequest('两次密码不一致')
        #     2.5 短信验证码是否和redis中的一致
        redis_conn = get_redis_connection('default')
        redis_sms_code = redis_conn.get('sms:%s' % mobile)
        if redis_sms_code is None:
            return HttpResponseBadRequest('短信验证码已过期')
        if smscode != redis_sms_code.decode():
            return HttpResponseBadRequest('短信验证码不一致')
        # 3.保存注册信息
        # create_user 可以使用系统的方法来对密码进行加密
        try:
            user = User.objects.create_user(username=mobile,
                                            mobile=mobile,
                                            password=password)
        except DatabaseError as e:
            logger.error(e)
            return HttpResponseBadRequest('注册失败')

        from django.contrib.auth import login
        login(request, user)
        # 4.返回响应跳转到指定页面
        # 暂时返回一个注册成功的信息，后期再实现跳转到指定页面
        response=redirect(reverse('home:index'))
        #return HttpResponse('注册成功，重定向到首页')
        # 设置cookie信息，以方便首页中 用户信息展示的判断和用户信息的展示
        response.set_cookie('is_login', True)
        response.set_cookie('username', user.username, max_age=7 * 24 * 3600)
        return response


class ImageCodeView(View):

    def get(self,request):
        """
        1.接收前端传递过来的uuid
        2.判断uuid是否获取到
        3.通过调用captcha 来生成图片验证码（图片二进制和图片内容）
        4.将 图片内容保存到redis中
            uuid作为一个key， 图片内容作为一个value 同时我们还需要设置一个实效
        5.返回图片二进制
        :param request:
        :return:
        """
        # 1.接收前端传递过来的uuid
        uuid=request.GET.get('uuid')
        # 2.判断uuid是否获取到
        if uuid is None:
            return HttpResponseBadRequest('没有传递uuid')
        # 3.通过调用captcha 来生成图片验证码（图片二进制和图片内容）
        text,image=captcha.generate_captcha()
        # 4.将 图片内容保存到redis中
        #     uuid作为一个key， 图片内容作为一个value 同时我们还需要设置一个实效
        redis_conn = get_redis_connection('default')
        # key 设置为 uuid
        # seconds  过期秒数  300秒 5分钟过期时间
        # value  text
        redis_conn.setex('img:%s'%uuid,300,text)
        # 5.返回图片二进制
        return HttpResponse(image,content_type='image/jpeg')
from django.http.response import JsonResponse
from utils.response_code import RETCODE
import logging
logger=logging.getLogger('django')
from random import randint
from libs.yuntongxun.sms import CCP

class SmsCodeView(View):

    def get(self,request):
        """
        1.接收参数
        2.参数的验证
            2.1 验证参数是否齐全
            2.2 图片验证码的验证
                连接redis，获取redis中的图片验证码
                判断图片验证码是否存在
                如果图片验证码未过期，我们获取到之后就可以删除图片验证码
                比对图片验证码
        3.生成短信验证码
        4.保存短信验证码到redis中
        5.发送短信
        6.返回响应
        :param request:
        :return:
        """
        # 1.接收参数 （查询字符串的形式传递过来）
        mobile=request.GET.get('mobile')
        image_code=request.GET.get('image_code')
        uuid=request.GET.get('uuid')
        # 2.参数的验证
        #     2.1 验证参数是否齐全
        if not all([mobile,image_code,uuid]):
            return JsonResponse({'code':RETCODE.NECESSARYPARAMERR,'errmsg':'缺少必要的参数'})
        #     2.2 图片验证码的验证
        #         连接redis，获取redis中的图片验证码
        redis_conn=get_redis_connection('default')
        redis_image_code=redis_conn.get('img:%s'%uuid)
        #         判断图片验证码是否存在
        if redis_image_code is None:
            return JsonResponse({'code':RETCODE.IMAGECODEERR,'errmsg':'图片验证码已过期'})
        #         如果图片验证码未过期，我们获取到之后就可以删除图片验证码
        try:
            redis_conn.delete('img:%s'%uuid)
        except Exception as e:
            logger.error(e)
        #         比对图片验证码, 注意大小写的问题， redis的数据是bytes类型
        if redis_image_code.decode().lower() != image_code.lower():
            return JsonResponse({'code':RETCODE.IMAGECODEERR,'errmsg':'图片验证码错误'})
        # 3.生成短信验证码
        sms_code= '%06d'%randint(0,999999)
        # 为了后期比对方便，我们可以将短信验证码记录到日志中
        logger.info(sms_code)
        # 4.保存短信验证码到redis中
        redis_conn.setex('sms:%s'%mobile,300,sms_code)
        # 5.发送短信
        # 参数1： 测试手机号
        # 参数2：模板内容列表： {1} 短信验证码   {2} 分钟有效
        # 参数3：模板 免费开发测试使用的模板ID为1
        CCP().send_template_sms(mobile,[sms_code,5],1)
        # 6.返回响应
        return JsonResponse({'code':RETCODE.OK,'errmsg':'短信发送成功'})
class LoginView(View):

        def get(self,request):

            return render(request,'login.html')
        def post(self,request):
            """
                    1.接收参数
                    2.参数的验证
                        2.1 验证手机号是否符合规则
                        2.2 验证密码是否符合规则
                    3.用户认证登录
                    4.状态的保持
                    5.根据用户选择的是否记住登录状态来进行判断
                    6.为了首页显示我们需要设置一些cookie信息
                    7.返回响应
                    :param request:
                    :return:
                    """
            # 1.接收参数
            mobile = request.POST.get('mobile')
            password = request.POST.get('password')
            remember = request.POST.get('remember')
            # 2.参数的验证
            #     2.1 验证手机号是否符合规则
            if not re.match(r'^1[3-9]\d{9}$', mobile):
                return HttpResponseBadRequest('手机号不符合规则')
            #     2.2 验证密码是否符合规则
            if not re.match(r'^[a-zA-Z0-9]{8,20}$', password):
                return HttpResponseBadRequest('密码不符合规则')
            # 3.用户认证登录
            # 采用系统自带的认证方法进行认证
            # 如果我们的用户名和密码正确，会返回user
            # 如果我们的用户名或密码不正确，会返回None
            from django.contrib.auth import authenticate
            # 默认的认证方法是 针对于 username 字段进行用户名的判断
            # 当前的判断信息是 手机号，所以我们需要修改一下认证字段
            # 我们需要到User模型中进行修改，等测试出现问题的时候，我们再修改
            user = authenticate(mobile=mobile, password=password)

            if user is None:
                return HttpResponseBadRequest('用户名或密码错误')
            # 4.状态的保持
            from django.contrib.auth import login
            login(request, user)
            # 5.根据用户选择的是否记住登录状态来进行判断
            # 6.为了首页显示我们需要设置一些cookie信息

            # 根据next参数来进行页面的跳转
            # next_page = request.GET.get('next')
            # if next_page:
            #     response = redirect(next_page)
            # else:
            response = redirect(reverse('home:index'))

            if remember != 'on':  # 没有记住用户信息
                # 浏览器关闭之后
                request.session.set_expiry(0)
                response.set_cookie('is_login', True)
                response.set_cookie('username', user.username, max_age=14 * 24 * 3600)
            else:  # 记住用户信息
                # 默认是记住 2周
                request.session.set_expiry(None)
                response.set_cookie('is_login', True, max_age=14 * 24 * 3600)
                response.set_cookie('username', user.username, max_age=14 * 24 * 3600)

            # 7.返回响应
            return response

from django.contrib.auth import logout
class LogoutView(View):
    def get(self,request):
        # 1.session数据清除
        logout(request)
        # 2.删除部分cookie数据
        response = redirect(reverse('home:index'))
        response.delete_cookie('is_login')
        # 3.跳转到首页
        return response


