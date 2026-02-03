#pragma once
#include <JuceHeader.h>
#include "PluginProcessor.h" // Required to access the real audio engine

class AudioPlayer : public juce::Component,
                    public juce::ChangeListener
{
public:
    enum TransportState {
        Stopped,
        Starting,
        Playing,
        Stopping
    };
    
    TransportState state;
    
    // 1. Constructor: Now accepts the Processor reference
    AudioPlayer (SoundSiftAudioProcessor& p)
        : processor (p)
    {
        addAndMakeVisible(playButton);
        playButton.setButtonText("Play");
        playButton.onClick = [this] { playButtonClicked(); };
        
        addAndMakeVisible(stopButton);
        stopButton.setButtonText("Stop");
        stopButton.onClick = [this] { stopButtonClicked(); };
        stopButton.setEnabled(false);
        
        // 2. Listen to the PROCESSOR'S transport source, not a local one
        processor.transportSource.addChangeListener(this);
    }
    
    ~AudioPlayer() override
    {
        processor.transportSource.removeChangeListener(this);
    }
    
    // 3. Load File: Passes the request to the Processor
    void loadFile(const juce::File& file)
    {
        processor.loadFile(file); // This loads it into the real audio engine
        currentFile = file;       // Keep this local just to draw the name on screen
        repaint();
    }
    
    // Note: prepareToPlay, getNextAudioBlock, and releaseResources were removed.
    // They are no longer needed here because the Processor handles the audio now.
    
    void paint(juce::Graphics& g) override
    {
        g.fillAll(getLookAndFeel().findColour(juce::ResizableWindow::backgroundColourId));
        
        if (currentFile != juce::File())
        {
            g.setColour(juce::Colours::white);
            g.drawText(currentFile.getFileName(), getLocalBounds(), juce::Justification::centred);
        }
    }
    
    void resized() override
    {
        auto area = getLocalBounds();
        auto buttonArea = area.removeFromBottom(30);
        playButton.setBounds(buttonArea.removeFromLeft(buttonArea.getWidth() / 2).reduced(2));
        stopButton.setBounds(buttonArea.reduced(2));
    }
    
    void changeState (TransportState newState)
    {
        if (state != newState)
        {
            state = newState;
            switch (state)
            {
                case Stopped:
                    stopButton.setEnabled (false);
                    playButton.setEnabled (true);
                    processor.transportSource.setPosition (0.0);
                    break;
                    
                case Starting:
                    playButton.setEnabled (false);
                    processor.transportSource.start();
                    break;
                    
                case Playing:
                    stopButton.setEnabled (true);
                    break;
                    
                case Stopping:
                    processor.transportSource.stop();
                    break;
            }
        }
    }
    
private:
    // 4. Reference to the Main Processor
    SoundSiftAudioProcessor& processor;
    
    juce::TextButton playButton;
    juce::TextButton stopButton;
    juce::File currentFile; // Used only for display

    
    void playButtonClicked()
    {
        changeState (Starting);
    }
    
    void stopButtonClicked()
    {
        changeState (Stopping);
    }
    
    void changeListenerCallback(juce::ChangeBroadcaster* source) override
    {
        // 5. Check if the PROCESSOR'S transport changed
        if (source == &processor.transportSource)
        {
            if (processor.transportSource.isPlaying())
                changeState (Playing);
            else
                changeState (Stopped);
        }
    }
};
