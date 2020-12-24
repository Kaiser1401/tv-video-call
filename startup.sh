source $HOME/.bashrc
cd $HOME/tv-video-call
echo "--------- $(date) ---------" >> vidlog.txt
while ! ping -c 1 -W 1 8.8.8.8; do
    echo "Waiting for 8.8.8.8 - network interface might be down..." >> vidlog.txt
    sleep 1
done
git checkout update
git pull
python3 main.py --room $VIDROOM --user $VIDNAME --server $VIDSERVER >> vidlog.txt
