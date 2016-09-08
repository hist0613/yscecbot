# -*- encoding:utf-8 -*-
from __future__ import absolute_import

import os
import pickle
from urllib.parse import urlparse, parse_qs
import re
import time
import datetime

import requests
from bs4 import BeautifulSoup
from pyvirtualdisplay import Display
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
from slackclient import SlackClient

from settings import *

def krtime2datetime(text):
    # " - 2016년 9월 2일, 금요일, 오후 1:24"
    # " - 2016년 9월 3일, 토요일, 오후 10:12"
    # " - 2016년 8월 31일, 수요일, 오전 12:46"
    # " - 2016년 8월 30일, 화요일, 오후 3:59"
    # " - 2016년 8월 23일, 화요일, 오전 12:53"
    # " 씀"
    text = text.strip()
    if text == "씀":
        return datetime.datetime.now()
    text = text[2:]
    yyyymmdd, weekday, hhmm = [word.strip() for word in text.split(',')]
    yyyymmdd = datetime.datetime.strptime(yyyymmdd, "%Y년 %m월 %d일")
    hhmm = hhmm.replace("오전", "AM")
    hhmm = hhmm.replace("오후", "PM")
    hhmm = datetime.datetime.strptime(hhmm, "%p %I:%M")
    hhmm = datetime.timedelta(hours=hhmm.hour, minutes=hhmm.minute)
    return yyyymmdd + hhmm

def main(current_time):
    path = os.path.dirname(os.path.realpath(__file__))
    try:
        # 저장된 세션이 존재하는 경우
        with open(os.path.join(path, "user/{user_id}/session".format(user_id=STUDENT_ID)), 'rb') as fp:
            session = pickle.load(fp)

        # 저장된 세션이 존재하지만 로그인에 실패한 경우
        if session.get("http://yscec.yonsei.ac.kr/my/").url != "http://yscec.yonsei.ac.kr/my/":
            print("NotValidSession")
            raise Exception("NotValidSession")

    except:
        # 저장된 세션이 존재하지 않는 경우
        display = Display(visible=0, size=(800, 600))
        display.start()
        driver = webdriver.Firefox()
        driver.get("http://yscec.yonsei.ac.kr/login/index.php")
        username_input = WebDriverWait(driver, 5).until(
            expected_conditions.presence_of_element_located((By.ID, "username"))
        )
        username_input.clear()
        username_input.send_keys(STUDENT_ID)
        password_input = WebDriverWait(driver, 5).until(
            expected_conditions.presence_of_element_located((By.ID, "password"))
        )
        password_input.clear()
        password_input.send_keys(STUDENT_PW)
        password_input.send_keys(Keys.RETURN)

        time.sleep(3)

        # http://yscec.yonsei.ac.kr/my/ 로 이동하지 않았다면 로그인이 실패한 상황
        if driver.current_url != "http://yscec.yonsei.ac.kr/my/":
            print("Login Failed!")
            return

        # 속도 향상을 위해 selenium은 세션을 얻는 것 까지만 담당하고, 이후로는 requests 사용
        session = requests.Session()
        for cookie in driver.get_cookies():
            session.cookies.set(cookie['name'], cookie['value'])
        driver.close()
        display.stop()

        print("Login Success!")

        # 로그인 처리 후 세션 저장
        with open(os.path.join(path, "user/{user_id}/session".format(user_id=STUDENT_ID)), 'wb') as fp:
            pickle.dump(session, fp)

    try:
        with open(os.path.join(path, "user/{user_id}/already_noticed".format(user_id=STUDENT_ID)), 'rb') as fp:
            already_noticed = pickle.load(fp)
    except FileNotFoundError:
        already_noticed = set()

    sc = SlackClient(SLACK_TOKEN)
    if sc.rtm_connect():
        print("Connection success!")
    else:
        print("Connection Failed, invalid token?")
        return

    # 나의 YSCEC 처리, 과목 리스트 가져오기
    my_page = BeautifulSoup(session.get("http://yscec.yonsei.ac.kr/my/").text, "html.parser")
    for course in my_page.find_all('div', 'course_title'):
        course_link = course.a['href']
        course_title = course.a.text
        course_id = int(parse_qs(urlparse(course_link).query)['id'][0])

        print('\n' + course_title)

        message = "*" + course_title + " - 공지사항*\n"
        flag = 0

        # 과목별로 사용하는 게시판(forum)들이 다르기 때문에
        # 게시판(일반)을 클릭했을 때 나오는 페이지에서 게시판 목록을 가져옴
        forums_link = "http://yscec.yonsei.ac.kr/mod/jinotechboard/index.php?id={course_id}".format(course_id=course_id)
        forums_page = BeautifulSoup(session.get(forums_link).text, "html.parser")
        for forum in forums_page.tbody.find_all('tr'):
            forum_id = int(re.search(r'\d+', forum.a['href']).group())
            FORUM_BASE_URL = "http://yscec.yonsei.ac.kr/mod/jinotechboard/"
            forum_link = FORUM_BASE_URL + forum.a['href']
            forum_page = BeautifulSoup(session.get(forum_link).text, "html.parser")

            # 게시판 페이지에서 첫 화면에 보이는 글 목록을 가져오기
            posts = forum_page.find_all('div', 'thread-style')[0]
            posts = [post for post in posts.find_all('li') if post.get('class', [''])[0] != 'isnotice']
            for post in posts:
                # post_title = post.find_all('h1', 'thread-post-title')[0].a.text
                post_id = post.find_all('h1', 'thread-post-title')[0].a['onclick']
                post_id = int(re.search(r'\d+', post_id).group())

                # 글 상세 페이지 가져오기
                post_page = session.post("http://yscec.yonsei.ac.kr/mod/jinotechboard/content.php",
                            params={'b': forum_id, 'contentId': post_id, 'page': 1, 'perpage': 10, 'boardform': 1}).text
                post_page = BeautifulSoup(post_page, "html.parser")

                post_title = post_page.find_all('span', 'detail-title')[0].text
                post_date = post_page.find_all('span', 'detail-date')[0].text
                post_date = post_date.split(post_page.find_all('span', 'detail-date')[0].a.text)[-1]
                post_date = krtime2datetime(post_date)
                post_contents = post_page.find_all('div', 'detail-contents')[0].text

                if (course_id, forum_id, post_id) not in already_noticed:
                    # 보낼 메시지가 있음을 확인
                    flag = 1
                    # 보낸 메시지 목록에 추가
                    already_noticed.add((course_id, forum_id, post_id))
                    # 메시지 처리
                    message += " - %s|%s\n" % (post_date, post_title)
                    message += "   %s\n" % (' '.join(post_contents[:60].split('\n')))

                # print("제목: {}".format(post_title))
                # print("날짜: {}".format(krtime2datetime(post_date)))
                # print("내용: {}".format(post_contents[:100]))

        if flag:
            print(message)
            sc.rtm_send_message(channel="general", message=message)

            with open(os.path.join(path, "user/{user_id}/already_noticed".format(user_id=STUDENT_ID)), 'wb') as fp:
                pickle.dump(already_noticed, fp)

        message = "*" + course_title + " - 강의자료*\n"
        flag = 0

        # 강의 자료가 올라오는 것을 체크할 수 있어야함
        resources_link = "http://yscec.yonsei.ac.kr/course/resources.php?id={course_id}".format(course_id=course_id)
        resources_page = BeautifulSoup(session.get(resources_link).text.replace('<td colspan="3">', '<tr><td colspan="3">'), "html.parser")
        table = resources_page.find_all("table")[0]
        for tr in table.tbody.find_all('tr'):
            if 'r0' in tr.get('class', '') or 'r1' in tr.get('class', ''):
                resource = tr.find_all('td')
                resource_name = resource[1].a.text
                resource_link = resource[1].a['href']
                resource_description = resource[2].text

                if "folder" in resource_link:
                    resource_name += '/\n'
                    folder_page = BeautifulSoup(session.get(resource_link).text, "html.parser")
                    for resource in folder_page.find_all("span", "fp-filename"):
                        if resource.text.strip() != "":
                            resource_name += ' - ' + resource.text + '\n'

                if (course_id, resource_name) not in already_noticed:
                    flag = 1
                    already_noticed.add((course_id, resource_name))
                    message += resource_name + "\n"

        if flag:
            print(message)
            sc.rtm_send_message(channel="general", message=message)

            with open(os.path.join(path, "user/{user_id}/already_noticed".format(user_id=STUDENT_ID)), 'wb') as fp:
                pickle.dump(already_noticed, fp)


    # 세션은 기본적으로 저장해놓지만 저장된 세션이 계속 사용가능한지, 즉 로그인 성공인지 실패인지 다른 페이지에서도 확인할 수 있어야함
    #  - 로그인 실패인 경우 당사자에게 자동으로 slack message가 갈 수 있어야함
    # 새로운 공지사항, 강의자료, 과제 알림
    #  - Forum(general), Resources 이 2가지를 잘 살펴보며 될 듯
    # 과제 제출 남은 시간 알림 (일주일, 3일, 1일, 12시간, 6시간, 3시간, 1시간, 10분 단위)
    #  - 이건 시간을 계속 체크하기 보다는 celery나 cron을 이용해서 처리하는게 좋을 듯
    # 쪽지도 알림해줬으면 좋겠음. 쪽지 체크하는거 존나 귀찮 ㅅㅂ
    # Grades(점수)에 추가된 내용도 자동으로 알림해주면 좋을 듯

if __name__ == '__main__':
    main(datetime.datetime.now())
