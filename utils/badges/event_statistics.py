import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime
import logging
import traceback

logger = logging.getLogger(__name__)

# Global flag to control statistics generation
GENERATE_STATISTICS = False

class EventStatisticsReport:
    def __init__(self, output_dir="reports"):
        if not GENERATE_STATISTICS:
            logger.info("Statistics generation is disabled")
            return
            
        self.output_dir = output_dir
        logger.info(f"Initializing EventStatisticsReport with output directory: {output_dir}")
        
        try:
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                logger.info(f"Created output directory: {output_dir}")
        except Exception as e:
            logger.error(f"Failed to create output directory: {str(e)}")
            raise
        
        # Initialize statistics containers
        self.event_stats = {}
        self.form_responses = {}
        
    def collect_statistics(self, df):
        """Collect statistics from the DataFrame."""
        if not GENERATE_STATISTICS:
            logger.info("Statistics collection is disabled")
            return
            
        logger.debug("Collecting statistics from DataFrame")
        
        # Process each column that represents an event
        for col in df.columns:
            if '~' not in col:  # Main event columns
                if col not in ['Contact ID', 'First Name', 'Last Name', 'Title', 'Local Club']:
                    self._process_event_column(df, col)
            else:  # Form response columns
                self._process_form_response(df, col)
                
    def _process_event_column(self, df, col):
        """Process a single event column."""
        logger.debug(f"Processing event column: {col}")
        
        # Calculate statistics
        total_responses = len(df)
        yes_responses = len(df[df[col] == 'Yes'])
        no_responses = len(df[df[col] == 'No'])
        
        # Create pie chart
        plt.figure(figsize=(8, 6))
        plt.pie([yes_responses, no_responses], 
                labels=['Yes', 'No'],
                autopct='%1.1f%%')
        plt.title(f'Responses for {col}')
        
        # Save chart
        chart_filename = f"event_{col.replace(' ', '_')}.png"
        chart_path = os.path.join(self.output_dir, chart_filename)
        plt.savefig(chart_path)
        plt.close()
        logger.debug(f"Created chart: {chart_path}")
        
        # Store statistics
        self.event_stats[col] = {
            'total': total_responses,
            'yes': yes_responses,
            'no': no_responses,
            'chart': chart_filename
        }
        
        # Add club breakdown for 'Yes' responses
        if 'Local Club' in df.columns:
            club_stats = df[df[col] == 'Yes']['Local Club'].value_counts()
            self.event_stats[col]['club_breakdown'] = club_stats.to_dict()
            
    def _process_form_response(self, df, col):
        """Process a form response column."""
        logger.debug(f"Processing form response: {col}")
        
        # Get response distribution
        response_counts = df[col].value_counts()
        
        # Create pie chart for non-empty responses
        non_empty_responses = response_counts[response_counts.index != '']
        if len(non_empty_responses) > 0:
            plt.figure(figsize=(8, 6))
            plt.pie(non_empty_responses.values,
                   labels=non_empty_responses.index,
                   autopct='%1.1f%%')
            plt.title(f'Responses for {col}')
            
            # Save chart
            chart_filename = f"event_{col.replace(' ', '_').replace('~', '_')}.png"
            chart_path = os.path.join(self.output_dir, chart_filename)
            plt.savefig(chart_path)
            plt.close()
            logger.debug(f"Created chart: {chart_path}")
            
            # Store statistics
            self.form_responses[col] = {
                'responses': response_counts.to_dict(),
                'chart': chart_filename
            }
            
    def generate_report(self):
        """Generate a markdown report with the collected statistics."""
        if not GENERATE_STATISTICS:
            logger.info("Report generation is disabled")
            return None
            
        logger.info("Generating markdown report...")
        
        try:
            # Create report filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_filename = f"event_statistics_{timestamp}.md"
            report_path = os.path.join(self.output_dir, report_filename)
            
            with open(report_path, 'w', encoding='utf-8') as f:
                # Write header
                f.write("# Event Registration Statistics Report\n\n")
                f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                # Write event statistics
                f.write("## Event Registration Statistics\n\n")
                for event, stats in self.event_stats.items():
                    f.write(f"### {event}\n\n")
                    f.write(f"Total Responses: {stats['total']}\n")
                    f.write(f"- Yes: {stats['yes']} ({stats['yes']/stats['total']*100:.1f}%)\n")
                    f.write(f"- No: {stats['no']} ({stats['no']/stats['total']*100:.1f}%)\n\n")
                    
                    if 'club_breakdown' in stats:
                        f.write("#### Club Breakdown (Yes Responses)\n\n")
                        for club, count in stats['club_breakdown'].items():
                            f.write(f"- {club}: {count} ({count/stats['yes']*100:.1f}%)\n")
                        f.write("\n")
                
                # Write form response statistics
                if self.form_responses:
                    f.write("## Form Response Statistics\n\n")
                    logger.debug(f"Processing {len(self.form_responses)} form responses")
                    for question, stats in self.form_responses.items():
                        f.write(f"### {question}\n\n")
                        total = sum(count for count in stats['responses'].values() if count > 0)
                        for response, count in stats['responses'].items():
                            if response and count > 0:  # Only show non-empty responses
                                f.write(f"- {response}: {count} ({count/total*100:.1f}%)\n")
                        f.write("\n")
            
            logger.info(f"Saving report to: {report_path}")
            logger.info("Report generated successfully")
            
            # Clean up chart files
            logger.debug("Cleaning up chart files...")
            for event in self.event_stats.values():
                if 'chart' in event:
                    try:
                        chart_path = os.path.join(self.output_dir, event['chart'])
                        if os.path.exists(chart_path):
                            os.remove(chart_path)
                            logger.debug(f"Removed chart file: {event['chart']}")
                    except Exception as e:
                        logger.warning(f"Failed to remove chart file: {event['chart']} - {str(e)}")
                        
            for response in self.form_responses.values():
                if 'chart' in response:
                    try:
                        chart_path = os.path.join(self.output_dir, response['chart'])
                        if os.path.exists(chart_path):
                            os.remove(chart_path)
                            logger.debug(f"Removed chart file: {response['chart']}")
                    except Exception as e:
                        logger.warning(f"Failed to remove chart file: {response['chart']} - {str(e)}")
                        
            return report_path
                        
        except Exception as e:
            logger.error(f"Error generating report: {str(e)}")
            logger.debug(traceback.format_exc())
            raise