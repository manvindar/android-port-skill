import android.media.*;
public class Tone {
    public static void main(String[] a) throws Exception {
        int sr = 48000, n = sr * 3;
        short[] buf = new short[n];
        for (int i = 0; i < n; i++) buf[i] = (short) (Math.sin(2 * Math.PI * 440 * i / sr) * 12000);
        AudioTrack t = new AudioTrack.Builder()
            .setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build())
            .setAudioFormat(new AudioFormat.Builder().setEncoding(AudioFormat.ENCODING_PCM_16BIT).setSampleRate(sr).setChannelMask(AudioFormat.CHANNEL_OUT_STEREO).build())
            .setBufferSizeInBytes(sr * 4).build();
        System.out.println("state=" + t.getState());
        t.play();
        int w = t.write(buf, 0, n);
        System.out.println("written=" + w + " playState=" + t.getPlayState());
        Thread.sleep(3500);
        t.release();
        System.out.println("done");
    }
}
