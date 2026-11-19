import time, sys
from vieneu import Vieneu
t=time.time(); v=Vieneu(); print("load", round(time.time()-t,1), file=sys.stderr)
for label, vid in v.list_preset_voices(): print(label, "|", vid)
t=time.time(); a=v.infer("Xin chào các bạn, hôm nay chúng ta sẽ tìm hiểu về trí tuệ nhân tạo.", voice="Phạm Tuyên"); dt=time.time()-t
v.save(a,"smoke.wav"); print("dur", len(a)/48000, "gen", round(dt,2), "rtf", round(dt/(len(a)/48000),3))
