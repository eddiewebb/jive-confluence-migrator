#!/usr/bin/python

import requests
import json
from Crypto.Cipher import AES
import threading
import os
from src.ProcessQuestion import ProcessQuestion
import time


#get proerites
f = open('./config/config.js', 'r')
profile = os.getenv('ENVNAME', "test")
config = json.load(f)
print "Running against profile: " + profile
profile = config[profile]

#decrypt passwords - both key and ciphers are hex encoded, and must be decoded
key = os.getenv('ENCKEY').decode("hex")
key = AES.new(key,AES.MODE_ECB)
unpad = lambda s : s[0:-ord(s[-1])]
profile['jive_password'] =  unpad(key.decrypt(profile['jive_password'].decode('hex')))
profile['conf_password'] =  unpad(key.decrypt(profile['conf_password'].decode('hex')))


def deleteQuestion(url):
	print "Deleting " + url
	r = requests.delete(url,verify=False,auth=(profile['conf_username'], profile['conf_password']))
	print "Delete:" + str(r.status_code)

def purgeConfluence():
	sure = raw_input("Do you want to delete all existing Questions, in all spaces, in Confluence first?!  (y/n)")
	if sure == "y":
		print "Destroying ALLLLLL questions in confluence"
		url = profile['conf_baseUrl'] + "/rest/questions/1.0/search?limit=500&type=question"
		r = requests.get(url,verify=False,auth=(profile['conf_username'], profile['conf_password']))
		print "Result:" + str(r.status_code)
		questions = json.loads(r.text)
		threads = []
		for question in questions['results']:
			while len(threads) > 75:
				print "Waiting for ative threads to drop"
				time.sleep(5)
				for thread in threads:
					if not thread.isAlive():
						threads.remove(thread)
			thr = threading.Thread(target=deleteQuestion, args=([profile['conf_baseUrl'] + "/rest/questions/1.0/question/" + str(question['id'])]))
			thr.start() # will run "foo"
			threads.append(thr)
		for thread in threads:
			thread.join()
		print "All qurstions deleted."
	else:
		print "skipping delete, import will be addative"

def getJiveResponse(url):
	r = requests.get(url,auth=(profile['jive_username'], profile['jive_password']))
	jiveResponseWithoutStupidInvalidLine = r.text.replace("throw 'allowIllegalResourceCall is false.';", "")
	obj = json.loads(jiveResponseWithoutStupidInvalidLine)
	return obj


def processDiscussions(discussions):
	threads = []
	for i in discussions['list']:
		thr = ProcessQuestion(i,communityName,profile)
		thr.start()
		threads.append(thr)
	# end loop questions
	for thr in threads:
		thr.join()
	# waits for batch to finish before exiting function




#clear target space out, maybe unecessary, comment out
purgeConfluence()
# determine api ID for place (which awesomely doesn't match the ID used in the UI)
communityName = raw_input("Please enter community name as seen in URLs (i.e. 'team-astronauts'): ")
#communityName = 'cloud-foundry'
communityRef = None
placeSearchUrl = profile['jive_baseUrl'] + "/api/core/v3/search/places?filter=search(" + communityName + ")&fields=displayName"
matchingPlaces = getJiveResponse(placeSearchUrl)
for place in matchingPlaces['list']:
	if place['displayName'] == communityName:
		communityRef = place['resources']['self']['ref']
		print "Found place " + communityName + " with ref " + communityRef
		break

if communityRef is None:
	print "Unable to find Jive Community with name: " + communityName
	exit()

if not os.path.exists("results"):
    os.makedirs("results")

# loop through paged results from jive for list of all questions in space.
morePages = True
filterUrl = profile['jive_baseUrl'] + "/api/core/v3/contents?filter=place(" + communityRef + ")&filter=type(discussion)&count=50"
while morePages:
	print "Calling:" + filterUrl
	discussions = getJiveResponse(filterUrl)
	processDiscussions(discussions)

	try:
		filterUrl = discussions['links']['next']
		print "Grabbing next page of questions"
	except KeyError:
		morePages = False
		print "No more pages"
# end loop get all pages


print "all done!"
