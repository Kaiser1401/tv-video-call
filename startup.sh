cd /home/en/tv-video-call
git checkout update
git pull
python3 main.py --room $VIDROOM --user $VIDNAME --server $VIDSERVER > vidlog.txt
