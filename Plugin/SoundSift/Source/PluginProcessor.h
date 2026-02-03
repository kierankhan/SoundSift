#pragma once

#include <JuceHeader.h>

class SoundSiftAudioProcessor  : public juce::AudioProcessor
{
public:
    //==============================================================================
    SoundSiftAudioProcessor();
    ~SoundSiftAudioProcessor() override;

    //==============================================================================
    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override;
    #ifndef JucePlugin_PreferredChannelConfigurations
        bool isBusesLayoutSupported (const BusesLayout& layouts) const override;
       #endif
    void processBlock (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;

    //==============================================================================
    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override;

    //==============================================================================
    const juce::String getName() const override;
    bool acceptsMidi() const override;
    bool producesMidi() const override;
    bool isMidiEffect() const override;
    double getTailLengthSeconds() const override;

    //==============================================================================
    int getNumPrograms() override;
    int getCurrentProgram() override;
    void setCurrentProgram (int index) override;
    const juce::String getProgramName (int index) override;
    void changeProgramName (int index, const juce::String& newName) override;

    //==============================================================================
    void getStateInformation (juce::MemoryBlock& destData) override;
    void setStateInformation (const void* data, int sizeInBytes) override;

    //==============================================================================
    // PUBLIC AUDIO MEMBERS
    // We make these public so the Editor (GUI) can access them to load files/start/stop
    juce::AudioFormatManager formatManager;
    juce::AudioTransportSource transportSource;
    
    // Helper to load a file safely from the Editor
    void loadFile (const juce::File& file);

private:
    // This holds the actual audio data reader. It must stay alive as long as the source is playing.
    std::unique_ptr<juce::AudioFormatReaderSource> readerSource;
    
    //==============================================================================
    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (SoundSiftAudioProcessor)
};
