
import threading
import requests
import os
import json
import re
from datetime import datetime
requests.packages.urllib3.disable_warnings()



class ProcessQuestion(threading.Thread):

	def __init__(self, jive,communityName,profile):
		threading.Thread.__init__(self)
		self.jive = jive
		self.communityName = communityName
		self.profile = profile
		## some aspects like "likes" in jive have no dates, use right now.
		self.now = datetime.now().isoformat()

	def replaceBodyContentsWithConfluenceImages(self, questionId, question):	
		imageMatchGroups = re.finditer("(" + self.profile['jive_baseUrl'] + "/servlet/JiveServlet/downloadImage/[a-zA-Z0-9/._-]*?/([a-zA-Z0-9._-]*?)\.(png|PNG|jpg|JPG|jpeg|JPEG))",question['body'])

		if imageMatchGroups:
			for image in imageMatchGroups:
				imgUrl = image.group(1)
				print "Downloading Image: " + imgUrl
				#grab from my connections
				response = requests.get(imgUrl,auth=(self.profile['jive_username'], self.profile['jive_password']))
				if response.status_code == 200:
					formData = {'file':response.content}
					headers = {'X-Atlassian-Token': 'nocheck'}
					#imgJson = {"filename":"jiveImage_" + image.group(2)}
					# uplioad to Confluence
					attachmentUrl = self.profile['conf_baseUrl'] + "/rest/api/content/" +  str(questionId) + "/child/attachment"
					print "attmtping post to " + attachmentUrl
					att = requests.post(attachmentUrl,verify=False,auth=(self.profile['conf_username'], self.profile['conf_password']),files=formData, headers=headers)
					# replace URL
					if att.status_code == 200:
						print "   Published attachement " + imgUrl + " to confluence question: " + str(questionId)	
						attInfo = json.loads(att.text)
						newUrl = attInfo['results'][0]['_links']['download']
						oldDownloadUrl = imgUrl
						oldShowUrl = imgUrl.replace("downloadImage","showImage",1)
						# now edit content (replacing both show and download links
						newBody = question['body'].replace(oldShowUrl,newUrl).replace(oldDownloadUrl,newUrl)
						updateQuestionUrl = self.profile['conf_baseUrl'] + "/rest/questions/1.0/question/" +  str(questionId)
						payload = {"body":newBody}
						print "target: " + updateQuestionUrl
						print "payload: " + json.dumps(payload)
						upd = requests.put(updateQuestionUrl,verify=False,auth=(self.profile['conf_username'], self.profile['conf_password']),json=json.dumps(payload), headers=headers)
						if upd.status_code == 200:
							print "Successfully edited contents with new URLs"
						else:
							print "ERROR updating question content with new image URLs"
							print upd.text
					else:
						print "   ERROR attaching image to question " + str(questionId)
						print att.text

		else:
			print "No inline images to migrate"


	def run(self):
		if self.jive['question']:  #isQuestion
			print "Building jive discussion " + self.jive['id'] + " as confluence question"
			bounty = False
			# 'question' is a boolean in the jive api..clearly. Build a object for confluence
			question = {}
			question['body'] = self.jive['content']['text'] 
			question['title'] = self.jive['subject']
			question['author'] = self.jive['author']['jive']['username']
			question['dateAsked'] = self.jive['published']
			question['topics'] = []
			# add default topic for migration and by community name
			topic = {}
			topic['id'] = 63406085
			topic['name'] = "jivemigration"
			question['topics'].append(topic)
			topic = {}
			topic['name'] = self.communityName
			question['topics'].append(topic)
			#get tags and categories as topics too
			if len(self.jive['tags']) > 0:
				for tag in self.jive['tags']:
					topic = {}
					topic['name'] = tag
					question['topics'].append(topic)
			if len(self.jive['categories']) > 0:
				for category in self.jive['categories']:
					topic = {}
					topic['name'] = category
					question['topics'].append(topic)
			# if answered, get answer
			question['answers'] = []
			if self.jive['resolved'] == "resolved":
				janswer = self.getJiveResponse(self.jive['answer'])
				answer = {}
				answer['author'] = janswer['author']['jive']['username']
				answer['accepted'] = True
				answer['body'] = janswer['content']['text']
				answer['dateAnswered'] = janswer['published']
				answer['dateAccepted'] = janswer['updated']
				if janswer['likeCount'] > 0:
					votes = []
					likes = self.getJiveResponse(janswer['resources']['likes']['ref'])
					for like in likes['list']:
						vote = {}
						vote['type'] = "up"
						vote['author'] = like['jive']['username']					
						vote['creationDate'] = self.now
						votes.append(vote)
					answer['votes'] = votes
				question['answers'].append(answer)
			#get all other top-level answers
			messages = self.getJiveResponse(self.jive['resources']['messages']['ref'])
			for message in messages['list']:
				if message['answer'] == False: # we already got answer above
					answer = {}
					answer['author'] = message['author']['jive']['username']
					answer['body'] = message['content']['text']
					answer['dateAnswered'] = message['published']
					if message['likeCount'] > 0:
						votes = []
						likes = self.getJiveResponse(message['resources']['likes']['ref'])
						for like in likes['list']:
							vote = {}
							vote['type'] = "up"
							vote['author'] = like['jive']['username']					
							vote['creationDate'] = self.now
							votes.append(vote)
						answer['votes'] = votes
					question['answers'].append(answer)
				
			#get all upvotes
			if  self.jive['likeCount'] > 0:
				likes = self.getJiveResponse(self.jive['resources']['likes']['ref'])
				votes = []
				for like in likes['list']:
					vote = {}
					vote['author'] = like['jive']['username']
					vote['type'] = "up"
					vote['creationDate'] = self.now
					votes.append(vote)
				question['votes'] = votes



			createQuestionUrl = self.profile['conf_baseUrl'] + "/rest/questions/1.0/import/questions/"
			r = requests.post(createQuestionUrl,verify=False,auth=(self.profile['conf_username'], self.profile['conf_password']), json = question)
			if r.status_code == 200:
				# now add attachements, and edit content
				respPayload = json.loads(r.text)
				print "   Published question " + self.jive['id'] + " to confluence as question " + str(respPayload['id'])	
				#self.replaceBodyContentsWithConfluenceImages(respPayload['id'],question)
			else:
				print "   ERROR porting question" + self.jive['id'] + " question json from JIve can be found in results/importError_" + self.jive['id']
				target = open("results/importError_" + self.jive['id'], 'w')
				target.write(json.dumps(r.text))
				target.close()
		# end if isQuestion


	def getJiveResponse(self,url):
		r = requests.get(url,auth=(self.profile['jive_username'], self.profile['jive_password']))
		jiveResponseWithoutStupidInvalidLine = r.text.replace("throw 'allowIllegalResourceCall is false.';", "")
		obj = json.loads(jiveResponseWithoutStupidInvalidLine)
		return obj
