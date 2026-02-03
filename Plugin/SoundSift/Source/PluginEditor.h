#pragma once
#include <JuceHeader.h>
#include "PluginProcessor.h"
#include "ApiClient.h"
#include "AudioPlayer.h"

class SoundSiftAudioProcessorEditor : public juce::AudioProcessorEditor
{
public:
    SoundSiftAudioProcessorEditor (SoundSiftAudioProcessor&);
    ~SoundSiftAudioProcessorEditor() override;

    void paint (juce::Graphics&) override;
    void resized() override;

private:
    void embedButtonClicked();
    void searchTextChanged();
    void searchButtonClicked();
    void resultItemClicked(int index);
    
    SoundSiftAudioProcessor& audioProcessor;
    
    // UI Components
    juce::TextButton embedButton;
    juce::TextEditor searchBox;
    juce::TextButton searchButton;
    juce::ListBox resultsList;
    AudioPlayer audioPlayer;
    juce::Label statusLabel;
    
    // API Client
    ApiClient apiClient;
    
    // Search results
    juce::StringArray searchResults;
    int topK = 10;  // Number of results to return
    juce::Slider topKSlider;
    juce::Label topKLabel;
    
    std::unique_ptr<juce::FileChooser> fileChooser;
    
    // ListBox model
    class ResultsListBoxModel : public juce::ListBoxModel
    {
    public:
        ResultsListBoxModel(SoundSiftAudioProcessorEditor& owner) : owner(owner) {}
        
        int getNumRows() override
        {
            return owner.searchResults.size();
        }
        
        void paintListBoxItem(int rowNumber, juce::Graphics& g,
                            int width, int height, bool rowIsSelected) override
        {
            if (rowIsSelected)
                g.fillAll(juce::Colours::lightblue);
            
            g.setColour(juce::Colours::black);
            
            if (rowNumber < owner.searchResults.size())
            {
                juce::File file(owner.searchResults[rowNumber]);
                g.drawText(file.getFileName(), 5, 0, width - 10, height,
                          juce::Justification::centredLeft, true);
            }
        }
        
        void listBoxItemClicked(int row, const juce::MouseEvent&) override
        {
            owner.resultItemClicked(row);
        }
        
    private:
        SoundSiftAudioProcessorEditor& owner;
    };
    
    std::unique_ptr<ResultsListBoxModel> resultsModel;
    
    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (SoundSiftAudioProcessorEditor)
};
