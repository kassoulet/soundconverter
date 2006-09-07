#!/usr/bin/python

# batch mode tests

import glob
import os
import os.path
try: 
	from tunepimp import tunepimp, metadata, track
except ImportError:
	pass

destdir = "batch-results/"
srcdir = "snd/"

try:
	os.mkdir(destdir)
except:
	pass

def towav(filename):
	wav = filename + ".wav"
	filename = filename
	os.system("gst-launch-0.10 filesrc location=%s ! decodebin ! audioconvert ! wavenc ! filesink location=%s.wav " % (filename.replace(" ","\ "), wav.replace(" ","\ ")))
	return wav

def get_trm(filename):

	os.system("trm %s" % filename)
	return


for f in glob.glob(srcdir + "*"):

	if not os.path.isfile(f):
		continue

	srcsize = os.path.getsize(f)

	link = f.replace(srcdir, destdir)

	try:
		os.remove(link)
	except OSError:
		pass
	os.symlink("../"+f, link)

	dest = link.replace(".wav",".ogg")
	os.system("soundconverter --batch %s" % link)
	destwav = towav(dest)
	get_trm(destwav)

	dest = dest.replace(".ogg",".ogg.wav")
	destsize = os.path.getsize(dest)
	print srcsize, destsize





"""
	tp = tunepimp.tunepimp('pytrm', '0.0.1', tunepimp.tpThreadRead | tunepimp.tpThreadAnalyzer);
	tp.addFile(filename)

	done = 0
	while not done:

		ret, type, fileId, status = tp.getNotification();
		if not ret:
			sleep(.1)
			continue

		if type != tunepimp.eFileChanged:
			continue


		tr = tp.getTrack(fileId);
		tr.lock()
		trm = tr.getTRM()

		if status == tunepimp.eUnrecognized and trm == "":
			tr.setStatus(tunepimp.ePending)
		else:
			if status == tunepimp.eTRMLookup:
				print tr.getTRM()
				done = 1
			else:
				if status == tunepimp.eRecognized:
				   print "TRM read from file: ", tr.getTRM()
				   tp.identifyAgain(fileId)
				else:
				   if status == tunepimp.ePending:
					   pass
				   else:
					   if status == tunepimp.eError:
						   print "Error:", tp.getError()
						   done = 1

		tr.unlock()
		tp.wake(tr)
		tp.releaseTrack(tr);
"""
